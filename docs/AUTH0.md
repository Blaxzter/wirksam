# Auth0 Tutorial (WirkSam)

This project uses Auth0 for authentication. The frontend is a SPA using Auth0 Universal Login, and the backend validates JWT access tokens.

## Prerequisites

Install the Auth0 CLI:

```bash
# Using Scoop (Windows)
scoop install auth0

# Using Homebrew (macOS/Linux)
brew install auth0/auth0-cli/auth0

# Or download from: https://github.com/auth0/auth0-cli/releases
```

Login to your Auth0 tenant with required scopes:

```bash
auth0 login --scopes create:client_grants,read:users,update:users
```

## 1. Create Auth0 resources

### Option A: Using Auth0 CLI (Recommended)

```bash
# 1. Create the API (non-interactive)
# The API resource represents your backend and defines who can access it.
# Your backend will validate JWT tokens against this API's audience identifier.
# Note: Use your actual production domain as the identifier (e.g., https://api.yourdomain.com)
# This is a logical identifier, not an actual URL - it stays the same across all environments
#
# Don't have a domain yet? Use any unique identifier like:
# - https://api.myproject.dev
# - https://myproject-api.com (even if you don't own it)
# - https://api.myproject.local
# You can keep using this identifier even after getting a real domain
auth0 apis create \
  --name "Your Project API" \
  --identifier "https://api.yourdomain.com" \
  --signing-alg "RS256" \
  --token-lifetime 86400 \
  --scopes "" \
  --no-input \
  --json

# ✅ From output "IDENTIFIER" field, save to:
#    Backend:  AUTH0_AUDIENCE=https://api.yourdomain.com
#    Frontend: VITE_AUTH0_API_AUDIENCE=https://api.yourdomain.com

# 2. Create the SPA Application (non-interactive, reveals Client ID)
# This represents your frontend Vue.js app and defines where users can be redirected
# after login. The Client ID identifies your frontend to Auth0.
auth0 apps create \
  --name "Your Project Web" \
  --type "spa" \
  --callbacks "http://localhost:5173,http://localhost:5173/app/home" \
  --logout-urls "http://localhost:5173" \
  --web-origins "http://localhost:5173" \
  --no-input \
  --json

# ✅ From output "client_id" field, save to:
#    Frontend: VITE_AUTH0_CLIENT_ID=<client_id>
#
# Note: SPAs automatically get "authorization_code" grant type. Add "refresh_token" if needed:
# auth0 apps update <CLIENT_ID> --grants "authorization_code,refresh_token"

# 3. Create Machine-to-Machine App for Management API (reveals Client ID & Secret)
# This M2M app allows your backend to call Auth0's Management API to update user
# profiles, assign roles, etc. It uses client credentials (ID + secret) to authenticate.
auth0 apps create \
  --name "Your Project Backend M2M" \
  --type "m2m" \
  --reveal-secrets \
  --no-input \
  --json

# ✅ From output, save to backend .env:
#    Backend: AUTH0_CLIENT_ID=<client_id>
#    Backend: AUTH0_CLIENT_SECRET=<client_secret>

# 4. Authorize the M2M app to access Management API
# This grants your M2M app permission to read and update user data in Auth0.
# Without this, your backend won't be able to modify user profiles or roles.
# Replace YOUR_M2M_CLIENT_ID and YOUR_TENANT with your values:
auth0 api post "client-grants" \
  --data '{"client_id":"YOUR_M2M_CLIENT_ID","audience":"https://YOUR_TENANT.eu.auth0.com/api/v2/","scope":["read:users","update:users"]}'

# ✅ No env vars needed from this command (grants M2M app permissions)

# 5. Create admin role
# Roles allow you to control access to admin-only features in your application.
# Users with the 'admin' role will have elevated permissions in your app.
auth0 roles create \
  --name "admin" \
  --description "Administrator role with full access" \
  --no-input

# ✅ No env vars needed from this command (creates role for authorization)

# 6. Create a user and assign admin role
# Create your first admin user who can access all features of your application.
# First, create a user (replace with your email and password):
auth0 users create \
  --name "Admin User" \
  --email "admin@example.com" \
  --password "YourSecurePassword123!" \
  --connection-name "Username-Password-Authentication" \
  --no-input \
  --json

# Then assign the admin role to the user:
# Get the user_id from the output above, and role_id from step 5 output
auth0 users roles assign <USER_ID> --roles <ROLE_ID>

# Alternatively, if you already signed up via the UI, search for your user:
# auth0 users search --query "email:<your-email>"
# Then use the user_id from the results to assign the role

# ✅ Your tenant domain (visible in all outputs) should be saved to:
#    Backend:  AUTH0_DOMAIN=<your-tenant>.eu.auth0.com
#    Frontend: VITE_AUTH0_DOMAIN=<your-tenant>.eu.auth0.com
```

### Option B: Using Auth0 Dashboard (Manual)

In your Auth0 tenant:

1. Create an Application:

- Type: Single Page Application (SPA)
- Name: Your Project Web

2. Create an API:

- Name: Your Project API
- Identifier (Audience): `https://api.yourdomain.com` (use your actual production domain)
- Signing Algorithm: RS256
- Note: This identifier is a logical ID that stays the same across all environments
- Don't have a domain? Use any unique URL-like identifier (e.g., `https://api.myproject.dev`)

3. Enable RBAC (optional but recommended for admin features):

- API Settings -> RBAC: ON
- API Settings -> "Add Permissions in the Access Token": ON (optional)

4. Create Machine-to-Machine Application:

- Type: Machine to Machine
- Name: Your Project Backend M2M
- Authorize for Auth0 Management API with scopes: `read:users`, `update:users`

## 2. Configure callback and origin URLs

### Using CLI

If you need to update the URLs later:

```bash
# Update SPA application URLs
# IMPORTANT: Include /app/home callback - the frontend redirects users there after login
auth0 apps update <YOUR_SPA_CLIENT_ID> \
  --callbacks "http://localhost:5173,http://localhost:5173/app/home,https://your-production-domain.com,https://your-production-domain.com/app/home" \
  --logout-urls "http://localhost:5173,https://your-production-domain.com" \
  --web-origins "http://localhost:5173,https://your-production-domain.com"
```

### Using Dashboard

In Auth0 Application settings (SPA):

Allowed Callback URLs:

- `http://localhost:5173`
- `http://localhost:5173/app/home`
- `https://your-production-domain.com/app/home`

Allowed Logout URLs:

- `http://localhost:5173`

### Using CLI

Create the action file `add-roles-to-token.js`:

```js
exports.onExecutePostLogin = async (event, api) => {
    const namespace = "https://yourdomain.com";
    const roles = (event.authorization && event.authorization.roles) || [];
    api.accessToken.setCustomClaim(`${namespace}/roles`, roles);
};
```

Deploy the action:

```bash
# Create the action
auth0 actions create \
  --name "Add Roles to Access Token" \
  --trigger "post-login" \
  --code "$(cat add-roles-to-token.js)"

# Deploy the action
auth0 actions deploy <ACTION_ID>

# Note: You'll need to manually bind the action to the Login flow in the dashboard
# Auth0 CLI doesn't yet support binding actions to flows
```

### Using Dashboard

Allowed Web Origins:

- `http://localhost:5173`

If you run on different hosts, add those too.

> **Note:** The frontend's login flow redirects to `/app/home` after authentication. If you set `VITE_AUTH0_CALLBACK_URL` in your frontend `.env`, that exact URL must be in the allowed callbacks list. If unset, the default redirect is `{origin}/app/home`.

## 3. Add roles into access tokens (admin support)

The backend checks these claims for admin access:

- `roles`
- or `https://yourdomain.com/roles` (use your actual domain)

The easiest way to include roles is a Post Login Action.

Auth0 -> Actions -> Library -> Build Custom -> Post Login:

```js
exports.onExecutePostLogin = async (event, api) => {
    const namespace = "https://yourdomain.com";
    const roles = (event.authorization && event.authorization.roles) || [];
    api.accessToken.setCustomClaim(`${namespace}/roles`, roles);
};
```

Assign the Action to your Login Flow.

Create an Auth0 role named `admin` and assign it to users who should access admin routes.

## 4. Configure local environment variables

Backend `.env`:

```
AUTH0_DOMAIN=YOUR_TENANT.eu.auth0.com
AUTH0_AUDIENCE=https://api.yourdomain.com

# Optional (only required for Management API user profile updates)
AUTH0_CLIENT_ID=YOUR_MGMT_APP_CLIENT_ID
AUTH0_CLIENT_SECRET=YOUR_MGMT_APP_CLIENT_SECRET
```

Frontend `frontend/.env`:

```
VITE_AUTH0_DOMAIN=YOUR_TENANT.eu.auth0.com
VITE_AUTH0_CLIENT_ID=YOUR_SPA_CLIENT_ID
VITE_AUTH0_API_AUDIENCE=https://api.yourdomain.com
VITE_AUTH0_CALLBACK_URL=http://localhost:5173
VITE_API_URL=http://localhost:8000
```

## 5. Verify

1. Start backend and frontend.
2. Login via the UI.
3. Open browser devtools -> network -> confirm `Authorization: Bearer ...` is sent.
4. Call `GET /api/v1/me` and `GET /api/v1/events` to verify authentication.
5. Admin users should see admin routes in the UI; backend enforces role checks.

## Troubleshooting

- 401/403 on backend: verify `AUTH0_AUDIENCE` matches your API identifier.
- No admin access: verify roles claim is present in the access token.
- CORS issues: ensure frontend origin is in backend `.env` or allowed in Auth0 SPA settings.
