# Android 17 Support for ToyVo/nixos-avf — Design

- Date: 2026-10-29
- Fork: `ToyVo/nixos-avf` (jj VCS, trunk synced to `upstream/trunk@d0a62c3`)
- Target: Pixel 10a, stock Android 17, unrooted, personal use, clear instructions
- Base nixpkgs: `nixos-unstable` (per owner request 2026-10-29, not 25.11)
- Upstream base: `nix-community/nixos-avf`, stalled, broken on Android 17 Terminal (`ferrochrome/5100000`)

## Intent / Why

Upstream `nixos-avf` only boots on Android 15/16 Terminal (EFI `efi_part` + `root_part` + `vm_config.json`, mTLS `ttyd` on TCP 7681, legacy guest agents).
Android 17 Terminal boots host `vmlinuz` directly with `root=/dev/vda1`, runs `/sbin/init`, exposes a read-only `cidata` ISO (`/dev/disk/by-label/cidata`) instead of `internal` VirtioFS, and expects `ttyd` over a UNIX socket bridged via VSOCK 7681 plus `linux_vm_manager`.
Goal: one fork that builds a bootable initial image for Android 17 while keeping a path back to upstream, with install steps a non-expert can follow on stock hardware.

## Goals

1. Bootable `image-*.tar.gz` (aarch64) for Android 17 Terminal on Pixel 10a, unrooted in-place install.
2. `sudo nixos-rebuild switch` exits 0 with 0 failed units (`systemctl --failed`) on device.
3. Working terminal UI (ttyd via VSOCK bridge), SSH/port-forwarding (`tcpstates-libbpf` + `linux_vm_manager`), graphics (`avf.enableGraphics`, weston) verified checklist.
4. Merge upstream fixes so trunk isn't behind:
   - PR #46 `xela-zone:feat/android-17` (4 commits, `avf/default.nix` + `initial/replace.sh`) — core
   - PR #38 `sysedwinistrator:fix-config-update` — `cat > vm_config.json` not `mv` (AVF disallows recreate)
   - PR #39 `matt1432:deprecations` — `mesa.drivers` outputs guard + `services.resolved.settings.Resolve.DNSSEC` guard
   - PR #44 `yvt:patch-1` — `CROSS_SYSTEM=aarch64-linux` doc fix
   - PR #45 `mio-19:patch-2` — drop dead `boot.initrd.systemd.enable`
   - Issue #40 — `build_id` date-parse crash (preserve Debian `build_id` or fix format)
   - Issue #41 — missing `virtio-snd` (`CONFIG_SND_VIRTIO` + ALSA check)
5. Clear `README.md` install path for stock Android 17: download image → place under `/sdcard/linux/` → auto-install → resize → rebuild.
6. CI builds image artifacts on push (reuse `.github/workflows/image.yml`).

## Non-goals

- Fixing `nixos-avf-image-app` (separate repo) — only document which app version to use.
- Rooted `ro.debuggable` flow as primary path — document only as fallback.
- x86_64 emulator support beyond "best effort" (focus aarch64).
- Upstreaming back to `nix-community` in this task (follow-up PR later).

## Anti-goals

- Breaking Android 15/16 boot in `trunk` without an explicit 17-only branch.
- Shipping an image that boots but `nixos-rebuild switch` leaves failed `mnt-internal` / `nftables` units.
- Opaque install: no unexplained `adb shell` magic, every step must be copy-pasteable.

## Constraints

- Stock, unrooted Pixel 10a: installer runs as UID 1000 (`droid`) against VirtioFS `/mnt/shared`; EOPNOTSUPP as root. PR #46's approach (extract as `droid`, loop-mount, tmpfs pivot, `dd` to `/dev/vda1`) must be kept.
- Android 17 guest kernel lacks `CONFIG_NFT_FIB` → must keep `networking.firewall.checkReversePath = false`.
- No `efi_part` on 17: `/boot` may not be mounted → `system.build.installBootLoader` wrapper + `nofail,x-systemd.device-timeout=2s` on `/boot`, `nofail` on `/mnt/internal`, `/mnt/shared`, `ConditionPathExists=!/dev/disk/by-label/cidata` on `mnt-internal.mount`.
- `linux_vm_manager` binary comes from host `cidata` (`/mnt/cidata/root_files/usr/bin/linux_vm_manager`); needs NixOS compat symlinks (`sftp-server`, `ld-linux-aarch64.so.1`, `tcpstates-libbpf` wrapper). Guarded by `ConditionPathExists`.
- Kernel: `boot.kernelPackages = linuxPackages_6_1` unless `useGenericKernel`; AVF balloon/cpufreq patches only apply there.
- Build host: likely x86_64 → need `CROSS_SYSTEM=aarch64-linux` + emulated or remote aarch64 builder; 2G `additionalSpace`, pigz tar must stay `apache-commons-compress` compatible (no `--sparse`).
- VCS: `jj` (not bare `git`). All changes via `jj` working copy, `jj log` to verify.

## Approaches Considered

### A. Dual-stack trunk (chosen)

Cherry-merge PR #46 + #38/#39/#44/#45 onto `trunk`. Legacy units (`ttyd` mTLS, `avahi_ttyd`, `storage_balloon_agent`, `forwarder_guest_launcher`, `shutdown_runner`) gated on `ConditionPathExists=/mnt/internal/ca.crt`; new units (`ttyd_uds`, `ttyd_vsock_bridge`, `linux_vm_manager`) gated on `!/mnt/internal/ca.crt`. `replace.sh` keeps `step_1/step_2` and adds `install_android17()` dispatched on `! -e $VM_LOC/vm_config.json`.
Trades: most code (conditions everywhere), but one image boots 15/16/17, minimal divergence, easiest to upstream later.

### B. 17-only hard fork (deferred)

Delete legacy services and `step_1/step_2`, keep only 17 path. Smaller, fewer failure modes, clearer for solo use. Rejected for now because it kills 15/16 compat and makes future upstream merges painful.

### C. Two-track now (variant of A)

Do A on `trunk`, then immediately cut `android17-only` branch that strips legacy (B on top of A). Kept as Phase 2 — user explicitly wants this branch eventually, but not before 10a boots.

## What we decided

- Go with A now, plan C-Phase-2 after verification on Pixel 10a.
- Branching (jj): `trunk` gets the merge; new jj bookmark `android17` tracks PR #46 base for testing, then a follow-up bookmark `android17-only` for the strip-down. User approves before any `jj git push`.
- Scope includes small PRs + #40/#41 investigation, not just #46 verbatim. If #41 needs kernel `SND_VIRTIO` + `SND`/`SOUND` already present in `avf/default.nix` `structuredExtraConfig`, verify with `aplay -l` on device; if missing, add module.
- Docs are deliverable, not afterthought: rewrite `README.md` Android 17 section + `initial/README-image.md`.

## What's left to the builder (plan will resolve)

- Exact merge order and conflict resolution (nixfmt churn in #46 vs #38/#39 overlapping hunks in `avf/default.nix`).
- Whether to keep `boot.initrd.systemd.enable = true` (removed by #45) — verify on `nixos-25.11` whether option still exists or warns.
- `build_id` format fix for #40: keep Debian `build_id_nix` vs rewrite `finish.nix` date line (`nixos_avf/.../...-0-$(date)` whitespace sensitivity).
- Image build + smoke test method without physical device in CI (`nix flake check`, `nix build .#initialImage`, `nixos-rebuild dry-build`).
- Release tagging for fork (`ToyVo` releases vs `nix-community` URLs in `initial/default.nix` `urlAVF` default).

## Verification (human on Pixel 10a)

1. `nix build .#initialImage` (aarch64) succeeds.
2. In-place replace reboots to NixOS, `systemd-growfs-root` expands (expect up to ~214G per PR notes, or device size).
3. `systemctl --failed` == 0, `ttyd_uds`, `ttyd_vsock_bridge`, `linux_vm_manager`, `nftables`, `sshd` active.
4. Terminal app shows shell; `sudo nixos-rebuild switch` clean; SSH port-forward works; `weston` display works if `enableGraphics`.
5. README steps followed verbatim on stock phone without root.
