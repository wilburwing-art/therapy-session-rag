# TherapyRAG — Patient Mobile App

Expo + expo-router (React Native, TypeScript strict) client for patients.
A patient taps a magic-link email from their therapist, which opens this
app via the `therapyrag://` URL scheme, signs them in against the same
FastAPI backend the web app uses, and drops them into a chat grounded in
their own session history.

## Layout

```
mobile/
├── app/
│   ├── _layout.tsx   # Root Stack + deep-link handler
│   ├── index.tsx     # Landing / "waiting for your link"
│   ├── chat.tsx      # Chat screen (FlatList + TextInput)
│   └── sessions.tsx  # Patient's own sessions
├── components/
│   ├── Message.tsx
│   ├── CitationCard.tsx
│   └── CrisisBanner.tsx
├── lib/
│   ├── api.ts          # fetch wrapper, injects Cookie header
│   ├── auth.ts         # redeemMagicLink / getSession / clearSession
│   └── secure_store.ts # typed wrapper around expo-secure-store
└── types.ts            # mirrors src/models/domain
```

## Setup

Requires Node 20+ and the Expo CLI via `npx`.

```bash
cd mobile
npm install
cp .env.example .env     # then edit EXPO_PUBLIC_API_URL
```

### Environment

| Variable              | Example                         | Notes                                                    |
| --------------------- | ------------------------------- | -------------------------------------------------------- |
| `EXPO_PUBLIC_API_URL` | `https://api.therapyrag.dev`    | Base URL of the FastAPI backend. No trailing slash.      |

For local development against a laptop-hosted backend, use your LAN IP
(e.g., `http://192.168.1.42:8000`) so the phone can reach it —
`localhost` resolves to the phone itself.

## Local dev

```bash
npx expo start
```

Scan the QR code with Expo Go (iOS Camera app or the Expo Go Android app)
or press `i` / `a` to open a simulator.

## Deep-link testing

The scheme is `therapyrag` and the sign-in path is
`therapyrag://chat?t=<MAGIC_LINK_TOKEN>`.

Issue a magic link from the backend (as a therapist), copy the raw
token out of the `POST /auth/patient/magic-link` response, then:

```bash
# iOS simulator
xcrun simctl openurl booted 'therapyrag://chat?t=REPLACE_ME'

# Android emulator
adb shell am start -W -a android.intent.action.VIEW -d 'therapyrag://chat?t=REPLACE_ME' com.therapyrag.patient

# Expo dev client with an arbitrary URL (any platform)
npx uri-scheme open 'therapyrag://chat?t=REPLACE_ME' --ios
```

The email itself also embeds this deep link as a fallback to the web URL,
so tapping the link from the device's mail client will launch the app
once it is installed.

## Production build

EAS generates the native `ios/` and `android/` projects — they are not
checked into this repo.

```bash
npm install -g eas-cli
eas login
eas build --platform ios
eas build --platform android
```

Configure the App Store / Play Store bundle IDs via `app.json`
(`com.therapyrag.patient` on both).

## Test

`npm run typecheck` runs `tsc --noEmit`. There is no test runner wired
up yet; unit-test coverage for `lib/` lives on the backlog.

## Known gaps

- Push notifications for new session-ready events.
- Offline queue for messages sent while the network is down.
- Auth refresh flow — when the magic-link session expires we send the
  user back to the landing screen to ask for a fresh link.
