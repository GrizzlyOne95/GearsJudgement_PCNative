# Gears 3 Steam campaign co-op patch

This patch restores the missing Steam friends path in the PC campaign build and
keeps a guest reserved in the persistent party when campaign travel begins. It
contains source changes only; no game source, packages, or compiled binaries are
redistributed here.

## Baseline and target

- Target file:
  `Development/Src/OnlineSubsystemSteamworks/Src/OnlineSubsystemSteamworks.cpp`
- Baseline: the frozen pre-co-op copy at
  `_Backups/src-port-snapshot-20260824/OnlineSubsystemSteamworks/Src/OnlineSubsystemSteamworks.cpp`
- Baseline SHA-256:
  `D65976593A91186E91E81200EDF13A8CA2ED63B8A310DBB4FB7317CB821695E7`
- Patched source SHA-256:
  `86C4529EA54C5E57E68F72BAC8C7BC54C21209CD9F8D4469B17B010BA4241A66`

The January 2011 alpha has a related Steamworks implementation, but it is 29
lines different from the later local baseline. The patch therefore targets the
surviving pre-edit snapshot rather than claiming cross-drop compatibility.

Apply from the private build-tree root:

```powershell
git apply --check <repo>\patches\gears3-steam-coop\0001-steam-campaign-coop.patch
git apply <repo>\patches\gears3-steam-coop\0001-steam-campaign-coop.patch
```

## Behavior restored

- Initializes `ISteamMatchmaking` and maintains a friends-only lobby alongside
  the existing UE3 party session.
- Publishes the listen host's `g3pc://<LAN IP>:1000/` location to the lobby and
  implements the previously stubbed invite and join functions.
- Preserves the configured server port when resolving the local host address.
- Ignores the shared-Spacewar listen host's late self-denial and self-kick paths
  instead of tearing down a working session.
- Advertises the listen host only after the Steam game server is logged on and
  has a valid ID. `InitiateGameConnection` must return a nonzero authentication
  blob before the address is cached; failed attempts retry on a later tick.
- Converts a Steam lobby acceptance into the normal
  `OnGameInviteAccepted` event. Gears then runs
  `RequestPersistentPartyJoin` and reserves the guest before client travel.

The last two points close the review findings that caused `0.0.0.0`, invisible
invites, and guests disappearing when the host started a campaign map.

## Build

The verified private build used the Win32 Release configuration with editor
code disabled and Steamworks forced on:

```powershell
$env:VS90COMNTOOLS = '<Visual Studio 2008 Common7\Tools\>'
$env:UE3_WINDOWS_SDK_DIR = '<Windows SDK v6.0A>'
[Environment]::SetEnvironmentVariable('ue3.bForceSteamworks', 'true', 'Process')

Development\Intermediate\UnrealBuildTool\Release\UnrealBuildTool.exe `
  GearGame Win32 Release -NOEDITOR `
  -OUTPUT '<private output path>\GearGame-Campaign-Steam-coopfix-v2.exe'
```

Verified private executable:

- Size: `31,738,368` bytes
- SHA-256:
  `46D4F103A95DF4A47BFD08E8D0794732075B5DEE20E8DD08DB888FF83B0EC32F`

The executable is a compiled derivative and is intentionally not committed.

## Runtime requirements

Both PCs must use the same executable and run Steam under separate Steam
accounts. Launch with `-MULTIHOME=<LAN address>` so UE3 does not publish a
Hyper-V or WSL adapter. The campaign rebuild also requires its existing PC
beacon resolver, extended party-beacon timeouts, and startup command:

```text
setnopec GearLocalPlayer bPartyTypeIsSystemLink true
```

The host opens campaign co-op and sends a Steam invite. The guest accepts it or
uses Steam's Join Game action. Direct travel remains useful as a diagnostic
fallback:

```text
open <host LAN address>:1000
```

## Validation

- The patch applies cleanly to the recorded baseline and reproduces the live
  source content (line-ending differences ignored).
- The Win32 Release `-NOEDITOR` build completed successfully.
- The host installation passed executable-hash, config, launcher, adapter, and
  stale-process preflight checks.
- A two-PC campaign transition and four-minute connection test remains required;
  the guest PC was offline during build verification.

Expected evidence in `GearGame/Logs/Launch.log`:

```text
Advertised listen host <IP>:1000 to Steam (server id <valid>, auth bytes <N>)
Steam lobby <id> dispatching Gears party invite for <IP>:1000
Created party beacon (PersistentPartyHost)
```

`server id [0:1]`, an advertisement failure that never retries, a direct lobby
travel without the invite event, or a host `ForceKickPlayer` call are failures.
