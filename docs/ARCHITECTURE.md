# Architecture — EquiTask AI

## Technology decision

Modular monolith. Python FastAPI + Pydantic + SQLAlchemy + PostgreSQL; local tests use SQLite. OR-Tools CP-SAT is an in-process authoritative library. Redis, durable workflows (e.g. Temporal) and Next.js are planned for later slices when operational need is demonstrated. The current runnable UI is accessible static HTML served by FastAPI; this is an explicit scope limitation, not a claim that Next.js is implemented.

## 1. System context

```mermaid
flowchart LR
    V[Volunteer] --> UI[EquiTask UI]
    O[Verified organization coordinator] --> UI
    A[Administrator] --> UI
    UI --> API[EquiTask API]
    API --> DB[(PostgreSQL / local SQLite)]
    API --> SOLVER[OR-Tools CP-SAT]
    API -. later .-> LLM[Controlled LLM gateway]
    API -. later .-> OBJ[(Object storage)]
    API -. later .-> MQ[(Redis / durable jobs)]
```

## 2. Container architecture

```mermaid
flowchart TB
    subgraph Client
      B[Static accessible UI / later Next.js]
    end
    subgraph App
      F[FastAPI application]
      P[Policy engine]
      S[Allocation service + CP-SAT]
      M[Domain state machine]
      G[Typed agent adapters - propose only]
    end
    subgraph Data
      D[(SQL database)]
      C[(Cache / idempotency - later)]
    end
    B --> F
    F --> M --> D
    F --> S --> P
    S --> P
    G -. typed drafts .-> F
    F -. later .-> C
```

## 3. Component architecture

```mermaid
flowchart TB
    API[API routers] --> AUTH[Auth / RBAC]
    API --> VAL[Pydantic validation]
    API --> SVC[Domain services]
    SVC --> EPI[Epistemic audit]
    SVC --> CAND[Candidate generator]
    SVC --> ALLOC[Allocation engine]
    ALLOC --> MODEL[CP-SAT model builder]
    ALLOC --> DIAG[Infeasibility diagnostics]
    ALLOC --> MET[Fairness metrics]
    SVC --> SM[Assignment/proposal state machine]
    SM --> AUDIT[Audit log]
    SVC --> REPAIR[Recovery planner]
    AG[Agent contracts] -.-> SVC
```

## 4. Multi-agent interaction sequence

```mermaid
sequenceDiagram
    participant O as Organization
    participant API as API
    participant I as Task Intake Agent
    participant C as Clarification Agent
    participant P as Allocation Planner
    participant S as CP-SAT Solver
    participant V as Volunteer
    participant E as Audit/Explanation Agent
    O->>API: submit project description
    API->>I: untrusted text, typed output contract
    I-->>API: DraftTask + missing_fields (no publish authority)
    API->>C: epistemic audit
    C-->>API: targeted questions (may not invent answers)
    API->>P: validated AllocationProblem
    P->>S: typed model + policy version
    S-->>P: proposals / infeasibility / unknown
    P-->>API: AllocationResult
    API->>E: solver output + permitted evidence
    E-->>V: explanation
    V->>API: accept / decline with idempotency key
    API->>API: revalidate + state transition + audit
```

## 5. Allocation pipeline

```mermaid
flowchart LR
    A[Typed input] --> B[Dependency cycle check]
    B --> C[Candidate generation]
    C --> D[Epistemic audit]
    D --> E[Clarification questions]
    E --> F[CP-SAT model]
    F --> G{Status}
    G -- OPTIMAL/FEASIBLE --> H[Proposals + metrics]
    G -- INFEASIBLE --> I[Reason codes]
    G -- UNKNOWN --> J[Safe no-op]
```

## 6. Database ER diagram

```mermaid
erDiagram
    USER ||--o| VOLUNTEER : has
    USER ||--o| ORG_MEMBERSHIP : has
    ORGANIZATION ||--o| ORG_MEMBERSHIP : has
    ORGANIZATION ||--o| PROJECT : owns
    PROJECT ||--o| TASK : contains
    TASK ||--o| TASK_SKILL : requires
    SKILL ||--o| TASK_SKILL : used_in
    VOLUNTEER ||--o| VOLUNTEER_SKILL : declares
    SKILL ||--o| VOLUNTEER_SKILL : used_in
    VOLUNTEER ||--o| AVAILABILITY_WINDOW : has
    VOLUNTEER ||--o| PREFERENCE : has
    TASK ||--o| ALLOCATION_PROPOSAL : receives
    VOLUNTEER ||--o| ALLOCATION_PROPOSAL : receives
    ALLOCATION_PROPOSAL ||--o| CONSENT_EVENT : records
    ALLOCATION_PROPOSAL ||--o| ASSIGNMENT : creates
    ASSIGNMENT ||--o| DELIVERABLE : has
    DELIVERABLE ||--o| REVIEW : has
    TASK ||--o| CONSTRAINT_EVALUATION : evaluated_by
    AGENT_RUN ||--o| WORKFLOW_EVENT : emits
    AUDIT_LOG }o--|| USER : actor
    RESEARCH_EXPERIMENT ||--o| ALLOCATION_RUN : records
```

## 7. Assignment state machine

```mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> VALIDATED: validation gate
    VALIDATED --> OFFERED: solver proposal
    OFFERED --> ACCEPTED: recorded consent
    OFFERED --> DECLINED: recorded decline
    OFFERED --> EXPIRED: timeout / infeasible
    ACCEPTED --> PENDING_APPROVAL: org approval required
    ACCEPTED --> ACTIVE: no approval required
    PENDING_APPROVAL --> ACTIVE: approval recorded
    PENDING_APPROVAL --> DECLINED: approval refused
    ACTIVE --> SUBMITTED: deliverable uploaded
    SUBMITTED --> UNDER_REVIEW
    UNDER_REVIEW --> COMPLETED: accepted by org
    UNDER_REVIEW --> DISPUTED: dispute opened
    DISPUTED --> UNDER_REVIEW: resolved
    ACTIVE --> WITHDRAWN: consented withdrawal
    WITHDRAWN --> [*]
    COMPLETED --> [*]
```

## 8. Failure and recovery flow

```mermaid
flowchart TD
    E[Event received] --> IDEM{Duplicate key?}
    IDEM -- yes --> RET[Return stored result]
    IDEM -- no --> TX[Begin transaction]
    TX --> VAL{Valid transition + constraints?}
    VAL -- no --> REJ[Reject + reason + audit]
    VAL -- yes --> COMMIT[Commit event + state]
    COMMIT --> OUT[Emit event at least once]
    OUT --> WORK[Worker retries idempotently]
    WORK --> DLQ[Repeated failure -> dead letter + human escalation]
```

## 9. Deployment architecture

```mermaid
flowchart TB
    GH[GitHub Actions CI] --> IMG[Docker image]
    IMG --> APP[App service]
    APP --> PDB[(PostgreSQL managed)]
    APP --> SEC[Secrets manager]
    APP --> LOG[Structured logs / tracing]
    APP --> STORE[(Object storage - later)]
```

## 10. Trust boundary and data flow

```mermaid
flowchart LR
    subgraph Untrusted
      UT[User text / filenames / task descriptions]
    end
    subgraph AppTrusted
      V[Pydantic validator]
      PO[Policy engine]
      SO[CP-SAT solver]
      SM[State machine]
    end
    subgraph ExternalSemi
      LM[LLM provider - optional]
    end
    UT --> V --> PO --> SO --> SM
    UT -. never direct .-> SM
    LM --> OUT[Typed candidate output]
    OUT --> V
    PO -->|least privilege| LM
```

Rules:
- Untrusted text is delimited and never given tool authority.
- Agent output must pass Pydantic + policy validation before any state change.
- Solver output is authoritative for feasibility; explanations never create rights.
- Organization tenant ID is checked on every query.

## Indexes and migrations

Initial indexes: `users.email` unique, `organizations.verification_status`, `tasks.project_id`, `tasks.status`, `allocation_proposals.task_id`, `allocation_proposals.volunteer_id`, `assignments.volunteer_id`, `audit_logs.created_at`. Migrations are managed by Alembic; retention and deletion policies are specified in `docs/THREAT_MODEL.md`.
