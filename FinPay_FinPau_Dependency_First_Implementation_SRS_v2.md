# FinPay / FinPau — Dependency-First Screen Implementation Specification

**Version:** 2.0  
**Status:** Implementation Blueprint  
**Architecture:** FastAPI + SQLAlchemy + Alembic + React/Vite + Socket.IO  
**Primary principle:** Build dependencies before dependent screens.  
**Real-time principle:** The database/domain event is the source of truth; Socket.IO is the real-time delivery mechanism.

---

## 1. Purpose

This document updates the FinPay/FinPau SRS implementation plan to include:

- Dependency-first implementation
- The original 13 SRS screens
- Expanded transactional screens
- Real-time notifications
- Socket.IO authentication and user rooms
- Transaction-specific real-time updates
- Persistent notification storage
- Reconnection and synchronization
- Wallet/transaction event architecture
- Idempotent financial operations
- FCM as a complementary background notification channel
- Offline/network recovery behavior

The objective is to implement the product as a production-oriented fintech application rather than building screens independently and connecting them later.

---

# 2. Core Architecture Principle

The system must follow:

```text
UI
 ↓
REST API / Socket.IO
 ↓
Application Services
 ↓
Domain/Event Services
 ↓
Database / External Providers
 ↓
Persisted Domain Event
 ↓
Notification/Event Dispatcher
 ↓
Socket.IO / FCM
 ↓
React UI
```

### Source-of-truth rule

Socket.IO must never be the financial source of truth.

For example:

```text
External Provider
      ↓
FastAPI
      ↓
Database Transaction
      ↓
Transaction Status = SUCCESS
      ↓
Transaction Event
      ↓
Notification
      ↓
Socket.IO
      ↓
Frontend
```

The frontend must not determine wallet balances or transaction success merely because it received a socket event.

---

# 3. Technology Stack

## Backend

- Python
- FastAPI
- SQLAlchemy
- Alembic
- MySQL or PostgreSQL
- Redis
- Celery or equivalent worker
- JWT authentication
- Argon2 password hashing
- Socket.IO
- Pydantic v2

## Frontend

- React
- Vite
- JavaScript
- Socket.IO Client
- REST API client
- Protected routes
- Central application state

## Notification channels

1. Socket.IO — active application sessions
2. FCM — background/mobile push
3. Database — notification history and recovery

---

# 4. Dependency-First Implementation Order

Do not implement the screens strictly according to their visual numbering.

The implementation sequence is:

```text
01 Application Foundation
02 Database
03 Authentication/Security
04 Session Management
05 Socket.IO Infrastructure
06 Notification Infrastructure
07 Registration
08 OTP
09 Login
10 Password Recovery
11 Protected Routing
12 Dashboard
13 Wallet
14 Transaction Engine
15 Transaction Events
16 Notification Delivery
17 Services
18 Electricity Payment
19 Payment Processing
20 Transaction History
21 Send Money
22 Add Money
23 Withdraw
24 KYC
25 Profile/Security
26 Support/Disputes
27 Offline/Recovery
```

---

# 5. Original SRS Screen Inventory

The original MVP contains 13 baseline screens:

| ID | Screen |
|---|---|
| SCR-001 | Welcome / Landing |
| SCR-002 | Create Account — Sign-Up Method |
| SCR-003 | Create Account — Enter Details |
| SCR-004 | Phone Verification — OTP |
| SCR-005 | Account Created — Success |
| SCR-006 | Login |
| SCR-007 | Forgot Password |
| SCR-008 | Enter Reset Code |
| SCR-009 | Create New Password |
| SCR-010 | Password Updated — Success |
| SCR-011 | Home / Dashboard |
| SCR-012 | Services |
| SCR-013 | Electricity — Provider Selection |

These screens remain the baseline. Additional screens extend the SRS rather than replacing them.

---

# 6. Layer 0 — Application Foundation

## 6.1 Backend structure

```text
backend/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── exceptions.py
│   │   └── logging.py
│   │
│   ├── db/
│   │   ├── database.py
│   │   └── base.py
│   │
│   ├── models/
│   ├── schemas/
│   ├── repositories/
│   ├── services/
│   ├── dependencies/
│   ├── routers/
│   ├── events/
│   ├── notifications/
│   └── websocket/
│
└── alembic/
```

## 6.2 Frontend structure

```text
frontend/
├── src/
│   ├── api/
│   │   ├── client.js
│   │   ├── auth.js
│   │   ├── dashboard.js
│   │   ├── wallet.js
│   │   ├── transactions.js
│   │   ├── services.js
│   │   ├── notifications.js
│   │   └── billPayments.js
│   │
│   ├── pages/
│   ├── components/
│   ├── layouts/
│   ├── routes/
│   ├── hooks/
│   ├── services/
│   ├── store/
│   └── utils/
```

---

# 7. Database Dependency Order

## 7.1 Identity tables

Create first:

```text
users
user_credentials
otp_codes
password_reset_tokens
refresh_tokens
sessions
```

## 7.2 Device/session tables

```text
user_devices
socket_sessions
```

## 7.3 Wallet/ledger tables

```text
wallets
wallet_transactions
ledger_entries
```

## 7.4 Transaction tables

```text
transactions
transaction_events
idempotency_keys
```

## 7.5 Services

```text
service_categories
service_providers
service_configs
```

## 7.6 Bill payment tables

```text
bill_payment_transactions
electricity_customers
electricity_meter_validations
```

## 7.7 Notification tables

```text
notifications
notification_events
notification_deliveries
```

## 7.8 Support

```text
support_tickets
transaction_disputes
```

---

# 8. Core Database Requirements

## 8.1 users

Required fields:

```text
id
first_name
last_name
email
phone
password_hash
status
email_verified
phone_verified
created_at
updated_at
last_login_at
```

Suggested status values:

```text
PENDING_VERIFICATION
ACTIVE
SUSPENDED
LOCKED
CLOSED
```

---

# 9. Authentication Dependency

Authentication must be completed before protected screens are implemented.

```text
Registration
   ↓
OTP Verification
   ↓
Active User
   ↓
Login
   ↓
JWT
   ↓
Protected APIs
```

---

# 10. Screen SCR-001 — Welcome / Landing

## Purpose

Introduce the application and provide access to registration and login.

## Dependencies

- Application shell
- Frontend routing

## Actions

- Create account
- Login

## Acceptance Criteria

- User can navigate to registration.
- User can navigate to login.
- No authenticated API is required.

---

# 11. Screen SCR-002 — Create Account: Sign-Up Method

## API

```http
POST /api/v1/auth/register/initiate
```

## Request

```json
{
  "signup_method": "phone",
  "phone": "+237XXXXXXXXX"
}
```

## Dependencies

- User validation
- OTP service
- User repository

## Acceptance Criteria

- Valid phone/email is accepted.
- Existing account is detected.
- OTP is generated.
- OTP expiry is enforced.
- Rate limiting is enforced.

---

# 12. Screen SCR-003 — Create Account: Enter Details

## API

```http
POST /api/v1/auth/register
```

## Request

```json
{
  "signup_method": "phone",
  "phone": "+237XXXXXXXXX",
  "first_name": "John",
  "last_name": "Doe",
  "email": "john@example.com",
  "password": "********"
}
```

## Backend result

```text
User.status = PENDING_VERIFICATION
```

---

# 13. Screen SCR-004 — Phone Verification / OTP

## API

```http
POST /api/v1/auth/verify-otp
```

## Request

```json
{
  "phone": "+237XXXXXXXXX",
  "otp": "123456"
}
```

## Result

```text
OTP verified
     ↓
User activated
     ↓
Registration completed
```

## Acceptance Criteria

- Correct OTP activates the account.
- Incorrect OTP is rejected.
- Expired OTP is rejected.
- Maximum attempts are enforced.
- Resend cooldown is enforced.

---

# 14. Screen SCR-005 — Account Created Success

This is primarily a confirmation screen.

It must not independently create financial/account records.

---

# 15. Screen SCR-006 — Login

## API

```http
POST /api/v1/auth/login
```

## Request

```json
{
  "identifier": "+237XXXXXXXXX",
  "password": "********"
}
```

## Response

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": 1,
    "first_name": "John",
    "last_name": "Doe"
  }
}
```

## Dependency

Successful authentication becomes the dependency for:

```text
Dashboard
Wallet
Transactions
Services
Notifications
Profile
Security
```

---

# 16. Password Recovery Screens

## SCR-007 — Forgot Password

```http
POST /api/v1/auth/password-reset/request
```

```json
{
  "identifier": "+237XXXXXXXXX"
}
```

## SCR-008 — Enter Reset Code

```http
POST /api/v1/auth/password-reset/verify
```

```json
{
  "identifier": "+237XXXXXXXXX",
  "code": "123456"
}
```

Returns a short-lived reset token.

## SCR-009 — Create New Password

```http
POST /api/v1/auth/password-reset/complete
```

```json
{
  "reset_token": "...",
  "new_password": "********"
}
```

## SCR-010 — Password Updated

Confirmation screen.

Existing sessions may be revoked according to security policy.

---

# 17. Socket.IO Infrastructure

Socket.IO must be implemented before transactional real-time screens.

## Connection flow

```text
Login
 ↓
JWT
 ↓
Socket.IO Client
 ↓
Socket Authentication
 ↓
Validate JWT
 ↓
Extract user_id
 ↓
Join user:{user_id}
```

## User room

```text
user:{user_id}
```

Example:

```text
user:10245
```

The server must derive the user ID from the authenticated JWT.

The client must never be trusted to select another user's room.

---

# 18. Socket.IO Authentication

Conceptual flow:

```python
async def authenticate_socket(token):
    payload = decode_access_token(token)
    user_id = payload["sub"]

    user = await get_user(user_id)

    if not user or not user.is_active:
        raise AuthenticationError()

    return user
```

On successful connection:

```text
socket.id
    ↓
authenticated user
    ↓
user:{user_id}
```

---

# 19. Socket Connection States

The frontend must track:

```text
CONNECTING
CONNECTED
DISCONNECTED
RECONNECTING
AUTHENTICATION_FAILED
```

Optional UI indicator:

```text
● Live
```

or:

```text
● Reconnecting…
```

---

# 20. Notification Architecture

The notification system has three layers:

```text
                    Notification Service
                           │
                 ┌─────────┴─────────┐
                 ▼                   ▼
             Socket.IO              FCM
                 │                   │
           Foreground           Background
                 │                   │
                 └─────────┬─────────┘
                           ▼
                    Notification DB
```

## Rule

Every important notification must first be persisted.

Socket.IO is delivery, not storage.

---

# 21. notifications Table

Suggested fields:

```text
id
user_id
type
title
message
data
priority
is_read
created_at
read_at
```

Priority:

```text
LOW
NORMAL
HIGH
CRITICAL
```

---

# 22. notification_events Table

```text
id
event_id
user_id
event_type
payload
created_at
processed_at
```

This allows event processing and notification delivery to be traced.

---

# 23. user_devices Table

```text
id
user_id
device_id
device_type
push_token
socket_session_id
last_seen_at
is_active
created_at
```

Used for:

- Socket sessions
- FCM delivery
- Device management
- Security monitoring

---

# 24. Standard Real-Time Event Envelope

All Socket.IO domain events should follow a common structure.

```json
{
  "event_id": "evt_01J...",
  "event_type": "TRANSACTION_SUCCESS",
  "timestamp": "2026-09-14T18:42:10Z",
  "user_id": 10245,
  "data": {
    "transaction_id": "txn_98765",
    "status": "SUCCESS",
    "amount": 10000,
    "currency": "XAF"
  }
}
```

---

# 25. Event Naming Convention

## Authentication

```text
AUTH_SESSION_CREATED
AUTH_SESSION_REVOKED
NEW_LOGIN
NEW_DEVICE
PASSWORD_CHANGED
PIN_CHANGED
```

## Wallet

```text
WALLET_CREDITED
WALLET_DEBITED
WALLET_BALANCE_UPDATED
```

## Transactions

```text
TRANSACTION_CREATED
TRANSACTION_PENDING
TRANSACTION_PROCESSING
TRANSACTION_SUCCESS
TRANSACTION_FAILED
TRANSACTION_REVERSED
```

## Transfers

```text
TRANSFER_SENT
TRANSFER_RECEIVED
```

## Bill payments

```text
BILL_PAYMENT_CREATED
BILL_PAYMENT_PENDING
BILL_PAYMENT_SUCCESS
BILL_PAYMENT_FAILED
```

## Security

```text
ACCOUNT_RESTRICTED
ACCOUNT_UNLOCKED
```

---

# 26. Notification APIs

## Get notifications

```http
GET /api/v1/notifications
```

## Unread count

```http
GET /api/v1/notifications/unread-count
```

## Mark read

```http
PATCH /api/v1/notifications/{id}/read
```

## Mark all read

```http
PATCH /api/v1/notifications/read-all
```

---

# 27. Notification Real-Time Events

Socket.IO events:

```text
notification:new
notification:read
notification:updated
```

Example:

```json
{
  "event_id": "evt_123",
  "event_type": "notification:new",
  "timestamp": "2026-09-15T08:30:00Z",
  "data": {
    "notification_id": 44,
    "type": "TRANSACTION_SUCCESS",
    "title": "Payment Successful",
    "message": "Your electricity payment was successful.",
    "priority": "HIGH"
  }
}
```

---

# 28. Notification Recovery

A socket event can be missed.

Therefore:

```text
Application opens
      ↓
GET /notifications
      ↓
Connect Socket.IO
      ↓
Receive live events
```

If disconnected:

```text
Socket disconnected
      ↓
Reconnect
      ↓
Fetch unread notifications
      ↓
Synchronize local state
```

The application must never assume Socket.IO delivered every event.

---

# 29. Dashboard — SCR-011

## APIs

```http
GET /api/v1/me
GET /api/v1/wallet
GET /api/v1/dashboard/summary
GET /api/v1/transactions?limit=5
GET /api/v1/notifications/unread-count
```

## Real-Time Events

```text
WALLET_BALANCE_UPDATED
TRANSACTION_SUCCESS
TRANSACTION_FAILED
TRANSACTION_PENDING
notification:new
```

## Dashboard flow

```text
Login
 ↓
JWT
 ↓
Dashboard APIs
 ↓
Socket.IO connection
 ↓
Subscribe to user events
 ↓
Live dashboard updates
```

---

# 30. Wallet Architecture

Wallet balances must be derived from authoritative ledger operations.

Do not allow the frontend to modify balances.

```text
Transaction
 ↓
Ledger
 ↓
Wallet balance
 ↓
Persist
 ↓
WALLET_BALANCE_UPDATED
 ↓
Socket.IO
```

---

# 31. Transaction Engine

The transaction engine is a major dependency for all financial operations.

Required concepts:

```text
Transaction
Transaction Status
Ledger Entry
Transaction Event
Idempotency Key
Provider Reference
```

## Status

```text
CREATED
PENDING
PROCESSING
SUCCESS
FAILED
REVERSED
```

---

# 32. Transaction Events

Table:

```text
transaction_events
```

Fields:

```text
id
transaction_id
event_type
previous_status
new_status
payload
created_at
```

Example:

```text
TRANSACTION_CREATED
       ↓
TRANSACTION_PENDING
       ↓
TRANSACTION_PROCESSING
       ↓
TRANSACTION_SUCCESS
```

Every state transition must be persisted.

---

# 33. Idempotency

Every financial creation endpoint must support:

```http
Idempotency-Key: unique-client-generated-value
```

Example:

```json
{
  "provider_id": "eneo",
  "meter_number": "123456789",
  "amount": 10000,
  "idempotency_key": "idem_abc123"
}
```

If the same key is submitted again:

```text
Existing transaction?
       │
   ┌───┴───┐
  YES      NO
   │        │
Return     Create
existing   transaction
```

This prevents double charging caused by:

- Double taps
- Network retries
- API retries
- Reconnection
- Provider timeouts

---

# 34. Services — SCR-012

## API

```http
GET /api/v1/services
```

Example:

```json
{
  "services": [
    {
      "id": "electricity",
      "name": "Electricity",
      "enabled": true
    },
    {
      "id": "airtime",
      "name": "Airtime",
      "enabled": true
    }
  ]
}
```

The frontend should render services from the API rather than hard-coding the service catalog.

---

# 35. Electricity — SCR-013

## Provider API

```http
GET /api/v1/bill-payments/providers?category=electricity
```

The provider list becomes the dependency for the electricity form.

---

# 36. Expanded Electricity Flow

The original provider-selection screen should be expanded to:

```text
SCR-013 Provider Selection
       ↓
SCR-014 Meter / Customer Details
       ↓
SCR-015 Validate Meter
       ↓
SCR-016 Payment Review
       ↓
SCR-017 PIN/Biometric Confirmation
       ↓
SCR-018 Payment Processing
       ↓
SCR-019 Payment Success
       OR
SCR-020 Payment Failed
       ↓
SCR-021 Receipt
```

---

# 37. Electricity Meter Validation

## API

```http
POST /api/v1/bill-payments/electricity/validate
```

## Request

```json
{
  "provider_id": "eneo",
  "meter_number": "1234567890"
}
```

## Response

Example:

```json
{
  "validation_token": "val_123",
  "customer": {
    "name": "JOHN DOE",
    "meter_number": "1234567890"
  },
  "provider": {
    "id": "eneo",
    "name": "Electricity Provider"
  }
}
```

The validation token must be short-lived.

---

# 38. Electricity Payment Review

Display:

```text
Provider
Meter Number
Customer Name
Amount
Fee
Total
```

The review screen must not execute the payment.

---

# 39. PIN/Biometric Confirmation

## API

```http
POST /api/v1/bill-payments/electricity/confirm
```

Example:

```json
{
  "validation_token": "val_123",
  "amount": 10000,
  "pin": "1234"
}
```

The backend must:

1. Validate authentication.
2. Validate transaction limits.
3. Validate PIN/authorization.
4. Check available balance.
5. Check idempotency.
6. Create transaction.
7. Persist transaction event.
8. Initiate provider operation.
9. Return transaction ID.

---

# 40. Electricity Processing

Initial state:

```text
TRANSACTION_PROCESSING
```

Frontend:

```text
Payment Processing
       ↓
Subscribe to transaction
       ↓
Wait for real-time event
```

---

# 41. Transaction-Specific Socket Room

For detailed transaction processing, support:

```text
transaction:{transaction_id}
```

Example:

```text
transaction:98765
```

Events:

```text
transaction:created
transaction:pending
transaction:processing
transaction:success
transaction:failed
transaction:reversed
```

The user must only be allowed to subscribe to transactions they own or are otherwise authorized to access.

---

# 42. Electricity Success

When provider confirmation is received:

```text
Provider
 ↓
SUCCESS
 ↓
Database transaction update
 ↓
Ledger update
 ↓
Transaction event
 ↓
Notification
 ↓
Socket.IO
```

Frontend receives:

```json
{
  "event_type": "TRANSACTION_SUCCESS",
  "data": {
    "transaction_id": "txn_98765",
    "status": "SUCCESS",
    "amount": 10000,
    "currency": "XAF"
  }
}
```

The UI navigates to the success screen.

---

# 43. Electricity Failure

Failure event:

```text
TRANSACTION_FAILED
```

Payload:

```json
{
  "event_type": "TRANSACTION_FAILED",
  "data": {
    "transaction_id": "txn_98765",
    "status": "FAILED",
    "reason_code": "PROVIDER_TIMEOUT",
    "retryable": true
  }
}
```

The UI should offer:

- Retry where safe
- View transaction
- Contact support

Retrying must use a new transaction operation or controlled idempotent retry mechanism, never blindly duplicate a successful provider operation.

---

# 44. Transaction History

## API

```http
GET /api/v1/transactions
```

Filters:

```text
type
status
date_from
date_to
amount_min
amount_max
search
page
limit
```

---

# 45. Transaction Details

## API

```http
GET /api/v1/transactions/{transaction_id}
```

Response should include:

```text
Transaction ID
Type
Amount
Fee
Total
Status
Provider
Reference
Created At
Completed At
Failure Reason
```

Where appropriate, expose an event timeline:

```text
Created
 ↓
Pending
 ↓
Processing
 ↓
Success
```

---

# 46. Receipt

## API

```http
GET /api/v1/transactions/{transaction_id}/receipt
```

The receipt must only be generated for eligible transactions.

Suggested data:

```text
Receipt Number
Transaction ID
Date/Time
Customer
Service
Provider
Amount
Fee
Total
Status
Provider Reference
```

---

# 47. Real-Time Send Money Flow

Future screen sequence:

```text
Send Money
 ↓
Recipient
 ↓
Amount
 ↓
Review
 ↓
PIN/Biometric
 ↓
Transaction Created
 ↓
Processing
 ↓
Socket.IO
 ↓
Success/Failure
```

Events:

```text
TRANSFER_SENT
TRANSFER_RECEIVED
TRANSACTION_SUCCESS
TRANSACTION_FAILED
```

The recipient can receive:

```text
TRANSFER_RECEIVED
```

in real time.

---

# 48. Add Money

Flow:

```text
Add Money
 ↓
Funding Method
 ↓
Amount
 ↓
Review
 ↓
Authorization
 ↓
Processing
 ↓
Success/Failure
```

Wallet event:

```text
WALLET_CREDITED
```

followed by:

```text
WALLET_BALANCE_UPDATED
```

---

# 49. Withdraw

Flow:

```text
Withdraw
 ↓
Destination
 ↓
Amount
 ↓
Review
 ↓
Authorization
 ↓
Processing
 ↓
Success/Failure
```

Events:

```text
WALLET_DEBITED
TRANSACTION_PROCESSING
TRANSACTION_SUCCESS
TRANSACTION_FAILED
```

---

# 50. KYC

KYC should be implemented after the identity and transaction foundation.

Suggested screens:

```text
KYC Introduction
 ↓
Personal Information
 ↓
Address
 ↓
ID Type
 ↓
ID Upload
 ↓
Selfie/Liveness
 ↓
Review
 ↓
Submission
 ↓
KYC Status
```

Statuses:

```text
NOT_STARTED
IN_PROGRESS
SUBMITTED
UNDER_REVIEW
APPROVED
REJECTED
```

---

# 51. Profile and Security

Suggested screens:

```text
Profile
Settings
Security Center
Change Password
Change PIN
Biometrics
Devices/Sessions
Transaction Limits
```

Security events:

```text
NEW_LOGIN
NEW_DEVICE
PASSWORD_CHANGED
PIN_CHANGED
ACCOUNT_RESTRICTED
```

These should create persisted notifications.

---

# 52. FCM Integration

Socket.IO is preferred for active sessions.

FCM handles:

```text
App background
Mobile push
Socket disconnected
Critical alerts
```

Flow:

```text
Domain Event
     ↓
Notification Service
     ↓
Persist Notification
     ↓
Is user connected?
     │
 ┌───┴────┐
YES       NO
 │         │
Socket    FCM
```

Depending on product policy, FCM may also be used for critical events even when Socket.IO is connected.

---

# 53. Notification Deduplication

Every notification should have a unique event ID.

Example:

```text
evt_01JXYZ
```

Before processing:

```text
Event already processed?
       │
   ┌───┴───┐
  YES      NO
   │        │
Ignore     Process
```

This prevents duplicate notifications during retries.

---

# 54. Redis / Worker Dependency

For production deployments with multiple FastAPI instances:

```text
FastAPI Instance A
FastAPI Instance B
FastAPI Instance C
        │
        ▼
      Redis
        │
        ▼
 Socket.IO Event Distribution
```

Background operations:

```text
Celery
 ↓
Provider polling/reconciliation
 ↓
Transaction update
 ↓
Domain event
 ↓
Notification
```

This is particularly important for delayed payment-provider responses.

---

# 55. External Provider Timeout

Never immediately mark a financial transaction as failed solely because an external provider timed out.

Recommended state:

```text
REQUEST SENT
 ↓
PROVIDER TIMEOUT
 ↓
PENDING / UNKNOWN
 ↓
RECONCILIATION
 ↓
SUCCESS / FAILED / REVERSED
```

The user can receive:

```text
"Your payment is still being processed."
```

rather than being incorrectly told the transaction failed.

---

# 56. Reconciliation

A background reconciliation worker should periodically verify pending transactions.

```text
Pending Transaction
       ↓
Provider status inquiry
       ↓
Provider result
       ↓
Update transaction
       ↓
Ledger
       ↓
Event
       ↓
Notification
       ↓
Socket.IO
```

This protects the system from provider/network failures.

---

# 57. Offline / Network Recovery

The application must distinguish:

```text
Internet unavailable
Socket unavailable
API unavailable
Provider unavailable
```

These are not the same state.

Example:

```text
Internet
   │
   ├── REST API available
   └── Socket disconnected
```

The application should continue using REST while reconnecting Socket.IO.

After reconnect:

```text
Socket reconnect
 ↓
Fetch unread notifications
 ↓
Fetch active/pending transaction state
 ↓
Synchronize UI
```

---

# 58. Frontend Socket Service

Create one central Socket.IO service.

Conceptual structure:

```text
socketService.js

connect(token)
disconnect()
on(event, handler)
off(event, handler)
emit(event, payload)
subscribeToTransaction(id)
unsubscribeFromTransaction(id)
getConnectionState()
```

Do not create independent Socket.IO connections in every React screen.

Use one managed connection per authenticated application session.

---

# 59. React Real-Time State Flow

```text
Socket Event
     ↓
socketService
     ↓
Event handler
     ↓
Application state/store
     ↓
Dashboard / Notification / Transaction UI
```

Example:

```text
TRANSACTION_SUCCESS
        ↓
transaction store
        ↓
transaction detail
        ↓
dashboard recent transactions
        ↓
notification badge
```

---

# 60. API vs Socket Responsibilities

| Requirement | REST | Socket.IO |
|---|---:|---:|
| Login | Yes | No |
| Registration | Yes | No |
| Get dashboard | Yes | Optional live update |
| Get history | Yes | No |
| Create payment | Yes | No |
| Payment status | Yes | Yes |
| New notification | Recovery | Yes |
| Mark notification read | Yes | Optional event |
| Wallet balance | Yes | Live update |
| Transaction creation | Yes | Event |
| Transaction success | Query | Live event |
| Transaction failure | Query | Live event |
| Reconciliation | Backend | Event delivery |

---

# 61. Security Requirements

Socket.IO must enforce:

- JWT authentication
- Token validation
- User ownership
- Room authorization
- Rate limiting
- Connection limits
- Event validation
- No sensitive credentials in socket payloads
- No PIN/password transmission through notification events
- No cross-user room access
- Session revocation handling

Financial values received from sockets should be treated as informational state updates until verified against the API when required.

---

# 62. Audit Requirements

Record:

```text
Login
Logout
New device
Password change
PIN change
KYC change
Transaction creation
Transaction status changes
Wallet changes
Notification creation
Notification delivery
Provider responses
Provider reconciliation
```

Audit records should contain:

```text
actor
action
entity
entity_id
timestamp
IP/device metadata where appropriate
result
```

---

# 63. Error Handling

Standard API error envelope:

```json
{
  "success": false,
  "error": {
    "code": "INSUFFICIENT_BALANCE",
    "message": "Insufficient wallet balance.",
    "details": {}
  },
  "request_id": "req_123"
}
```

Socket errors should use a similar predictable structure.

---

# 64. Acceptance Criteria — Real-Time System

### RT-001

Authenticated users receive events only for their own account.

### RT-002

Unauthenticated socket connections are rejected.

### RT-003

Socket reconnection is automatic.

### RT-004

Missed notifications are recovered through REST.

### RT-005

Every financial state transition is persisted before notification delivery.

### RT-006

Duplicate event delivery does not create duplicate notifications.

### RT-007

Wallet balances are never determined solely by Socket.IO.

### RT-008

Transaction-specific subscriptions enforce ownership.

### RT-009

Provider timeout does not automatically produce an incorrect FAILED state.

### RT-010

Pending transactions can be reconciled.

### RT-011

A successful transaction produces a persistent notification.

### RT-012

A failed transaction produces a persistent notification.

### RT-013

A wallet credit/debit generates a wallet event.

### RT-014

The dashboard reflects live wallet/transaction changes.

### RT-015

FCM can deliver critical/background notifications when the active socket is unavailable.

---

# 65. Testing Strategy

## Unit tests

Test:

```text
JWT validation
OTP
Password hashing
Idempotency
Wallet calculations
Transaction state machine
Notification creation
Event serialization
Authorization
```

## API tests

Test:

```text
Registration
OTP
Login
Password reset
Wallet
Transactions
Services
Electricity
Notifications
```

## Socket.IO tests

Test:

```text
Connection
Authentication
Room assignment
Unauthorized room access
Event delivery
Reconnect
Duplicate events
Disconnect
Transaction subscriptions
```

## Integration tests

Example:

```text
Create user
 ↓
Login
 ↓
Connect Socket.IO
 ↓
Create transaction
 ↓
Provider mock
 ↓
Provider success
 ↓
Database update
 ↓
Event creation
 ↓
Notification creation
 ↓
Socket event
 ↓
Frontend receives success
```

---

# 66. Critical End-to-End Payment Test

```text
User Login
    ↓
Socket Connected
    ↓
Services
    ↓
Electricity
    ↓
Provider
    ↓
Meter Validation
    ↓
Review
    ↓
PIN
    ↓
Idempotency Check
    ↓
Transaction Created
    ↓
TRANSACTION_PENDING
    ↓
Provider Request
    ↓
TRANSACTION_PROCESSING
    ↓
Provider Response
    ↓
Database Commit
    ↓
Ledger Update
    ↓
TRANSACTION_SUCCESS
    ↓
Notification Persisted
    ↓
Socket.IO
    ↓
React Processing Screen
    ↓
Success Screen
    ↓
Receipt
```

---

# 67. Implementation Milestones

## M1 — Foundation

Deliver:

- FastAPI
- React/Vite
- Configuration
- Database
- SQLAlchemy
- Alembic
- Error handling
- Logging
- Docker development environment

## M2 — Authentication

Deliver:

- Registration
- OTP
- Login
- JWT
- Refresh tokens
- Sessions
- Password reset

## M3 — Socket.IO

Deliver:

- Socket server
- JWT authentication
- User rooms
- Connection state
- Reconnection
- Event envelope

## M4 — Notification System

Deliver:

- Notification models
- Notification service
- Event dispatcher
- Notification APIs
- Real-time notification UI
- Unread counts
- Recovery synchronization

## M5 — Wallet and Transactions

Deliver:

- Wallet
- Ledger
- Transactions
- Transaction state machine
- Idempotency
- Transaction events

## M6 — Services and Electricity

Deliver:

- Service catalog
- Provider catalog
- Meter validation
- Payment review
- PIN authorization
- Provider integration/mock
- Processing
- Success/failure
- Real-time transaction updates

## M7 — History and Receipts

Deliver:

- Transaction history
- Filters
- Transaction details
- Event timeline
- Receipts

## M8 — Additional Financial Operations

Deliver:

- Send Money
- Add Money
- Withdraw
- Request Money
- Beneficiaries

## M9 — Identity/Security

Deliver:

- KYC
- Profile
- Security center
- PIN
- Biometrics
- Device/session management
- Limits

## M10 — Operations

Deliver:

- Support
- Disputes
- Fraud/risk controls
- Reconciliation
- FCM
- Offline/recovery
- Maintenance/update states

---

# 68. Final Dependency Graph

```text
                    APPLICATION FOUNDATION
                             │
                             ▼
                         DATABASE
                             │
                             ▼
                    AUTHENTICATION
                             │
                             ▼
                      SESSION/JWT
                             │
               ┌─────────────┴─────────────┐
               ▼                           ▼
           REST APIs                   Socket.IO
               │                           │
               └─────────────┬─────────────┘
                             ▼
                       NOTIFICATIONS
                             │
                             ▼
                         WALLET
                             │
                             ▼
                     TRANSACTION ENGINE
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
              EVENT SYSTEM       LEDGER SYSTEM
                    │
                    ▼
              SERVICE CATALOG
                    │
                    ▼
             ELECTRICITY FLOW
                    │
                    ▼
            PROVIDER INTEGRATION
                    │
                    ▼
             TRANSACTION STATUS
                    │
             ┌──────┴───────┐
             ▼              ▼
         Socket.IO         FCM
             │              │
             └──────┬───────┘
                    ▼
                REACT UI
```

---

# 69. Definition of Done

A screen is not considered implemented merely because its React UI exists.

A screen is complete when:

```text
UI
 ↓
Route
 ↓
API contract
 ↓
Backend endpoint
 ↓
Validation
 ↓
Service layer
 ↓
Database operation
 ↓
Authorization
 ↓
Error handling
 ↓
Audit/event handling
 ↓
Real-time events where applicable
 ↓
Tests
 ↓
Acceptance criteria passed
```

For financial screens, additionally:

```text
Idempotency
+
Ledger
+
Transaction state
+
Provider handling
+
Reconciliation
+
Notification
+
Socket.IO
```

must be implemented.

---

# 70. Recommended Build Rule

Do not proceed to a dependent layer until the previous layer passes its automated tests.

```text
M1 PASS
 ↓
M2 PASS
 ↓
M3 PASS
 ↓
M4 PASS
 ↓
M5 PASS
 ↓
M6 PASS
 ↓
M7 PASS
 ↓
M8 PASS
 ↓
M9 PASS
 ↓
M10 PASS
```

This dependency-first approach minimizes rework and ensures that the FinPay/FinPau screens are backed by a coherent transaction, notification, security, and real-time architecture.

---

# 71. Service Fees

Every money-movement operation may carry a **service fee** that is added to (for
debits) or deducted from (for deposits) the transaction amount. Fees are not
hard-coded: they are configured in the Back Office (section 72) and are
**variable per operation**.

## 71.1 Fee-bearing operations

Each of the following operations has its own independently configurable fee:

```text
DEPOSIT (Add Money)
WITHDRAW
SEND_MONEY (Transfer)
ELECTRICITY (Utility)
AIRTIME
DATA
```

## 71.2 Fee models

An operation's fee rule uses one of the following models:

- **FLAT** — a single fixed fee regardless of amount.
- **PERCENTAGE** — a percentage of the amount (for example `2.5%`), with
  optional minimum and maximum fee clamps.
- **TIERED** — fixed fees per amount range, for example:

```text
0     – 1000 XAF  → 150 XAF
1001  – 1500 XAF  → 250 XAF
1501  – 5000 XAF  → 400 XAF
...
```

Amounts and fees are expressed in minor currency units internally; the Back
Office may present and accept values in major units.

## 71.3 Fee application

- The fee for an operation is resolved from the active fee rule for that
  operation and the requested amount.
- **Debits** (withdraw, transfer, utility, airtime, data): the wallet is
  charged `amount + fee`. The transaction records `amount` and `fee`; `total =
  amount + fee`.
- **Deposit** (add money): the fee is deducted from the deposit, so the wallet
  is credited `amount − fee`.
- The applied fee must be **persisted on the transaction** (`fee` column) and
  reflected in the ledger and receipts.
- The backend is authoritative: it re-computes and validates the fee on every
  request; a client-side estimate is never trusted for settlement.

## 71.4 Client experience

- On login the server returns the current fee and feature configuration; the
  client **caches** it.
- Before an operation is confirmed, the client uses the cached configuration to
  **display the service fee and the total** to the user without a round trip.
- When the request is sent, the backend re-computes the fee and settles using
  its own value (the client estimate is informational only).
- A fee-quote endpoint is also available so the client can refresh a quote for
  an operation and amount on demand.

## 71.5 Acceptance criteria

```text
FEE-001  Each fee-bearing operation has an independently configurable fee.
FEE-002  FLAT, PERCENTAGE, and TIERED fee models are supported.
FEE-003  Percentage fees support optional min/max clamps.
FEE-004  The fee is displayed to the client before confirmation.
FEE-005  The backend re-computes and applies the authoritative fee.
FEE-006  The applied fee is persisted on the transaction and receipt.
FEE-007  Debits charge amount + fee; deposits credit amount − fee.
FEE-008  Fee configuration is delivered on login and cacheable by the client.
```

---

# 72. Back Office (Administration) Management UI

The **Back Office (BO)** is an administration console, separate from the
customer-facing **front store**, that lets operators manage and control the
platform's features and fees. Access is restricted to users with an
administrator role.

## 72.1 Capabilities

- **Fee management** — create and edit the fee rule for each operation:
  choose the model (FLAT / PERCENTAGE / TIERED), set the percentage (and
  optional min/max), or manage tier rows (amount range → fee), and
  activate/deactivate a rule. Changes take effect immediately for subsequent
  operations.
- **Feature / service control** — enable or disable the services and
  operations exposed by the front store (for example Electricity, Airtime,
  Data, Send Money, Withdraw, Add Money). A disabled service is hidden from the
  front store and its operation is rejected by the backend.
- **Operational overview** — high-level metrics (users, transactions,
  processed volume, fees collected) for monitoring.

## 72.2 Security

- BO endpoints require an authenticated administrator (`is_admin`).
- All BO changes are recorded in the audit log (actor, action, entity, result).
- The front store and BO share the same authentication system but the BO UI is
  reachable only by administrators.

## 72.3 Acceptance criteria

```text
BO-001  Only administrators can access BO endpoints and UI.
BO-002  Admins can set a variable fee (flat/percentage/tiered) per operation.
BO-003  Fee changes apply immediately to new operations.
BO-004  Admins can enable/disable front-store services and operations.
BO-005  Disabling a service hides it from the front store and blocks its API.
BO-006  BO changes are audited.
BO-007  The BO exposes an operational overview of platform metrics.
```
