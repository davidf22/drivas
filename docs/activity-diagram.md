# Drivas — Activity Diagram

```mermaid
flowchart TD
    START([User opens chat]) --> AUTH{Logged in?}

    %% ── Anonymous visitor ──────────────────────────────────
    AUTH -- No --> GREET[AI greets visitor]
    GREET --> ROLE{Want to join as?}

    ROLE -- Client --> REG_C[AI collects:\nFirst name, Last name,\noptional email]
    REG_C --> CONFIRM_C{Confirm details?}
    CONFIRM_C -- No  --> REG_C
    CONFIRM_C -- Yes --> CREATE_C[Create Client account\nGenerate username + password]
    CREATE_C --> SHOW_CREDS_C[AI shows login credentials]
    SHOW_CREDS_C --> CLIENT_DASH

    ROLE -- Driver --> REG_D[AI collects:\nFirst name, Last name,\nLicense number,\noptional email]
    REG_D --> CONFIRM_D{Confirm details?}
    CONFIRM_D -- No  --> REG_D
    CONFIRM_D -- Yes --> CREATE_D[Create Driver account\nGenerate username + password]
    CREATE_D --> SHOW_CREDS_D[AI shows login credentials]
    SHOW_CREDS_D --> PENDING[Account awaiting\noperator verification]
    PENDING --> VERIFY{Operator verifies\nin Django Admin?}
    VERIFY -- No  --> PENDING
    VERIFY -- Yes --> DRIVER_DASH

    %% ── Authenticated user ─────────────────────────────────
    AUTH -- Yes --> ROLE_CHECK{User role?}
    ROLE_CHECK -- Client --> CLIENT_DASH
    ROLE_CHECK -- Driver --> DRIVER_DASH
    ROLE_CHECK -- Admin  --> ADMIN_DASH

    %% ── Client flow ────────────────────────────────────────
    CLIENT_DASH([Client Dashboard\nChat]) --> C_ACTION{What does client want?}

    C_ACTION -- Post a job --> COLLECT_JOB[AI collects:\nWork location\nEmployment type\nRequirements\nAgreed rate]
    COLLECT_JOB --> CONFIRM_JOB{Confirm job details?}
    CONFIRM_JOB -- No  --> COLLECT_JOB
    CONFIRM_JOB -- Yes --> POST_JOB[post_job tool\n→ Job created OPEN]
    POST_JOB --> FIND_DRIVERS[find_best_driver tool\n→ Top available drivers]
    FIND_DRIVERS --> NOTIFY_DRIVERS[notify_user tool\n→ Push job alert to\neach candidate driver]
    NOTIFY_DRIVERS --> WAIT_ACCEPT[Waiting for driver\nto accept...]

    WAIT_ACCEPT --> DRIVER_ACCEPTS{Driver accepts job?}
    DRIVER_ACCEPTS -- No  --> WAIT_ACCEPT
    DRIVER_ACCEPTS -- Yes --> JOB_HIRED[Job status → HIRED\nClient notified]
    JOB_HIRED --> WAIT_START[Waiting for job\nto start...]
    WAIT_START --> JOB_ACTIVE[Job status → ACTIVE\nClient notified]
    JOB_ACTIVE --> WAIT_END[Job in progress...]
    WAIT_END --> JOB_ENDED[Job status → ENDED\nClient notified]
    JOB_ENDED --> CLIENT_DASH

    C_ACTION -- View my jobs   --> MY_JOBS_C[get_my_jobs tool\n→ AI shows job list]
    MY_JOBS_C --> CLIENT_DASH

    C_ACTION -- Cancel a job   --> CANCEL_C[cancel_job tool\n→ Job CANCELLED\nDriver set Available]
    CANCEL_C --> CLIENT_DASH

    C_ACTION -- Ask a question --> SUPPORT_C[AI answers or\nescalates to operator]
    SUPPORT_C --> CLIENT_DASH

    %% ── Driver flow ────────────────────────────────────────
    DRIVER_DASH([Driver Dashboard\nChat]) --> D_ACTION{What does driver want?}

    D_ACTION -- Go available --> SET_AVAIL[set_driver_availability\navailable=true\n→ Status: Available]
    SET_AVAIL --> DRIVER_DASH

    D_ACTION -- Go offline --> SET_OFFLINE[set_driver_availability\navailable=false\n→ Status: Offline]
    SET_OFFLINE --> DRIVER_DASH

    D_ACTION -- Browse open jobs --> GET_JOBS[get_open_jobs tool\n→ AI lists open jobs]
    GET_JOBS --> D_ACTION

    D_ACTION -- Accept a job --> CHECK_AVAIL{Driver Available\n& Verified?}
    CHECK_AVAIL -- No  --> AVAIL_ERR[AI explains why\ndriver can't accept]
    AVAIL_ERR --> DRIVER_DASH
    CHECK_AVAIL -- Yes --> ACCEPT[accept_job tool\n→ Job HIRED\nDriver status: Busy]
    ACCEPT --> NOTIFY_CLIENT_A[notify_user tool\n→ Client notified]
    NOTIFY_CLIENT_A --> DRIVER_DASH

    D_ACTION -- Start job --> START[start_job tool\n→ Job ACTIVE]
    START --> NOTIFY_CLIENT_S[notify_user tool\n→ Client notified]
    NOTIFY_CLIENT_S --> DRIVER_DASH

    D_ACTION -- End job --> END[end_job tool\n→ Job ENDED\nDriver status: Available\nTotal jobs +1]
    END --> NOTIFY_CLIENT_E[notify_user tool\n→ Client notified]
    NOTIFY_CLIENT_E --> DRIVER_DASH

    D_ACTION -- Cancel job --> CANCEL_D[cancel_job tool\n→ Job CANCELLED\nDriver set Available]
    CANCEL_D --> DRIVER_DASH

    D_ACTION -- View my jobs --> MY_JOBS_D[get_my_jobs tool\n→ AI shows engagements]
    MY_JOBS_D --> DRIVER_DASH

    D_ACTION -- Ask a question --> SUPPORT_D[AI answers or\nescalates to operator]
    SUPPORT_D --> DRIVER_DASH

    %% ── Admin / Operator ───────────────────────────────────
    ADMIN_DASH([Django Admin]) --> ADMIN_ACTION{Admin task}
    ADMIN_ACTION -- Verify driver     --> MARK_VERIFIED[Set is_verified = True\nDriver can accept jobs]
    ADMIN_ACTION -- View chat history --> VIEW_HISTORY[ConversationHistory\nChatMessage logs]
    ADMIN_ACTION -- Manage jobs       --> MANAGE_JOBS[View / edit\nJobEngagement records]
    MARK_VERIFIED   --> ADMIN_DASH
    VIEW_HISTORY    --> ADMIN_DASH
    MANAGE_JOBS     --> ADMIN_DASH

    %% ── Styles ─────────────────────────────────────────────
    classDef startEnd fill:#1a1a2e,color:#fff,stroke:none,rx:20
    classDef decision fill:#fff4f4,stroke:#e94560,color:#1a1a2e
    classDef action   fill:#fff,stroke:#ddd,color:#1a1a2e
    classDef status   fill:#e8f5e9,stroke:#4caf50,color:#1a1a2e
    classDef notify   fill:#e3f2fd,stroke:#2196f3,color:#1a1a2e
    classDef admin    fill:#f3e5f5,stroke:#9c27b0,color:#1a1a2e

    class START,CLIENT_DASH,DRIVER_DASH,ADMIN_DASH,PENDING startEnd
    class AUTH,ROLE,ROLE_CHECK,CONFIRM_C,CONFIRM_D,CONFIRM_JOB,DRIVER_ACCEPTS,CHECK_AVAIL,VERIFY,C_ACTION,D_ACTION,ADMIN_ACTION decision
    class REG_C,REG_D,COLLECT_JOB,CANCEL_C,CANCEL_D,SET_AVAIL,SET_OFFLINE,GET_JOBS,MY_JOBS_C,MY_JOBS_D,SUPPORT_C,SUPPORT_D action
    class CREATE_C,CREATE_D,POST_JOB,ACCEPT,START,END,MARK_VERIFIED status
    class FIND_DRIVERS,NOTIFY_DRIVERS,NOTIFY_CLIENT_A,NOTIFY_CLIENT_S,NOTIFY_CLIENT_E notify
    class VIEW_HISTORY,MANAGE_JOBS admin
```

---

## Flow Summary

| Actor | Key Activities |
|-------|---------------|
| **Anonymous visitor** | Chat → Choose role → Register (AI-guided) → Receive credentials |
| **Client** | Post job → AI matches & notifies drivers → Track job status → Cancel if needed |
| **Driver** | Set availability → Browse jobs → Accept → Start → End |
| **AI Agent** | Onboarding, job posting, driver matching, notifications, customer support |
| **Operator (Admin)** | Verify drivers, view logs, manage jobs via Django Admin |

## Job Status Lifecycle

```
OPEN → HIRED → ACTIVE → ENDED
         ↓        ↓
      CANCELLED  CANCELLED
```
