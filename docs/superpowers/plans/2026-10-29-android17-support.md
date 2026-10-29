# Android 17 Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge upstream Android 17 support into ToyVo/nixos-avf trunk and produce a bootable Pixel 10a image with clear install docs.

**Architecture:** Dual-stack NixOS modules gated on `/mnt/internal/ca.crt` presence (legacy 15/16 vs new 17 `ttyd_uds`+VSOCK+`linux_vm_manager`), direct-boot `/sbin/init` wrapper, in-place `/dev/vda1` installer from tmpfs pivot.

**Tech Stack:** Nix flakes (`nixos-unstable`), NixOS modules (`avf/default.nix`), bash (`initial/replace.sh`), `jj` VCS, GitHub Actions image build.

**Spec:** `docs/superpowers/specs/2026-10-29-android17-design.md`

## Global Constraints

- Base nixpkgs MUST be `nixos-unstable` (not 25.11).
- Target MUST be stock unrooted Pixel 10a, Android 17 Terminal `ferrochrome/5100000`.
- `networking.firewall.checkReversePath = false` MUST be kept (guest kernel lacks `CONFIG_NFT_FIB`).
- `/boot`, `/mnt/internal`, `/mnt/shared` MUST have `nofail`; `mnt-internal.mount` MUST have `ConditionPathExists=!/dev/disk/by-label/cidata`.
- Installer as UID 1000 MUST avoid EOPNOTSUPP on VirtioFS; no large writes via virtiofs (use `dd` to block device).
- Image tar MUST stay `apache-commons-compress` compatible (no `--sparse`, pigz only).
- VCS MUST use `jj`; verify with `jj status` / `jj log`, not bare `git status`.
- One image MUST boot 15/16/17 on `trunk`; 17-only strip goes to separate bookmark only.

## Review Focus

- Stock Terminal with no `/mnt/internal/linux/vm_config.json` boots to NixOS login, not EFI shell — installer dispatches to `install_android17()` when file missing.
- `sudo nixos-rebuild switch` on device leaves `systemctl --failed` at 0 — legacy units skipped via `ConditionPathExists=/mnt/internal/ca.crt`, new units skipped via `!` path.
- Debian `build_id` date-parse crash from issue #40 does not recur — Terminal app parses our `build_id` without extra whitespace.
- `aplay -l` shows VirtIO SoundCard per issue #41, or failure is documented — `SND_VIRTIO` module present.
- README steps work verbatim copy-pasted on stock phone — `IMG_LOC` covers `/mnt/shared/Download/root_part[.zst]` and `/mnt/shared/nixos.tar.gz` naming.

---

### Task 1: Flake to nixos-unstable

**Files:**
- Modify: `flake.nix`
- Modify: `flake.lock` (regenerated)
- Test: `nix flake check --no-build` output

**Interfaces:**
- Consumes: nothing
- Produces: `inputs.nixpkgs.url = github:NixOS/nixpkgs/nixos-unstable` for all later tasks

- [ ] **Step 1: Update flake input to unstable**

In `flake.nix`, set `nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable"`.

- [ ] **Step 2: Regenerate lock and eval check**

Run: `nix flake update nixpkgs && nix flake check --no-build`
Expected: PASS (warnings about `boot.initrd.systemd.enable` allowed here, fixed in Task 4)

- [ ] **Step 3: Commit**

```bash
jj commit -m "chore: track nixos-unstable"
```

### Task 2: Dual-stack avf/default.nix (PR #46 core + #38/#39/#45)

**Files:**
- Modify: `avf/default.nix`
- Test: `nix eval .#nixosConfigurations` / `nix build .#initialImage --no-link` (aarch64 via builder)

**Interfaces:**
- Consumes: unstable nixpkgs from Task 1
- Produces: `systemd.services.{ttyd,avahi_ttyd,ttyd_uds,ttyd_vsock_bridge,linux_vm_manager}`, `system.activationScripts.avf_sbin_init`, `system.build.installBootLoader` wrapper, `fileSystems.{/boot,/mnt/cidata,/mnt/internal,/mnt/shared}` with `nofail`

- [ ] **Step 1: Gate legacy services on ca.crt**

In `avf/default.nix`, add to `systemd.services.ttyd`, `avahi_ttyd`, and `mkService` (`storage_balloon_agent`, `forwarder_guest_launcher`, `shutdown_runner`): `unitConfig.ConditionPathExists = "/mnt/internal/ca.crt"` (mkService uses `/mnt/internal/debian_service_port`).

- [ ] **Step 2: Add 17-only units ttyd_uds + vsock bridge**

Add `systemd.services.ttyd_uds` (`RuntimeDirectory=ttyd`, `ExecStart=${extraPkgs.ttyd}/bin/ttyd -i /run/ttyd/ttyd.sock ... /bin/login -f ${cfg.defaultUser}`, `ConditionPathExists="!/mnt/internal/ca.crt"`) and `ttyd_vsock_bridge` (`socat VSOCK-LISTEN:7681,fork,reuseaddr UNIX-CONNECT:/run/ttyd/ttyd.sock`, same condition, `requires=[ttyd_uds]`).

- [ ] **Step 3: Add linux_vm_manager with compat links**

Add `systemd.services.linux_vm_manager` gated on `[!/mnt/internal/ca.crt, /mnt/cidata/root_files/usr/bin/linux_vm_manager]`, `path=[coreutils systemd util-linux socat openssh bcc gnused kmod /run/current-system/sw]`, `preStart` creating `/usr/bin /usr/sbin /usr/lib/openssh /usr/libexec/openssh` symlinks for `sftp-server`, `ld-linux-aarch64.so.1` via `pkgs.stdenv.cc.bintools.dynamicLinker`, and `/usr/sbin/tcpstates-libbpf` wrapper (`insmod kheaders.ko || true; exec stdbuf -oL tcpstates | sed -u '1s/C-PID C-COMM/PID   COMM  /'`), `ExecStart=/mnt/cidata/root_files/usr/bin/linux_vm_manager`.

- [ ] **Step 4: Add direct-boot init + bootloader guard + mounts + firewall**

Add `system.activationScripts.avf_sbin_init` linking `/sbin/init` and `/init` to `/nix/var/nix/profiles/system/prepare-root`; wrap `system.build.installBootLoader` via `options.system.build.definitionsWithLocations` to only `exec ${origBuilder}` when `findmnt /boot` succeeds; set `fileSystems."/boot".options=["nofail" "x-systemd.device-timeout=2s"]`, add `/mnt/cidata` iso9660 `ro,nofail`, add `nofail` to `/mnt/internal`+`/mnt/shared`, add `systemd.mounts` override `where=/mnt/internal ConditionPathExists=!/dev/disk/by-label/cidata`; set `networking.firewall.checkReversePath=false`, `allowedTCPPorts=[22 2222 7681]`.

- [ ] **Step 5: Fold small PRs #38 #39 #45**

Apply: #38 `extraInstallCommands` uses `cat new > /mnt/internal/linux/vm_config.json` not `mv`; #39 `mesaDrivers = if builtins.elem "drivers" pkgs.mesa.outputs then pkgs.mesa.drivers else pkgs.mesa` for `LIBGL_DRIVERS_PATH`, `services.resolved = if hasAttr "settings" then {settings.Resolve.DNSSEC=false;} else {dnssec="false";}`; #45 delete `boot.initrd.systemd.enable`.

- [ ] **Step 6: Format + eval verify**

Run: `nix fmt -- --check . 2>&1 || nixfmt --check avf/default.nix; nix flake check --no-build`
Expected: PASS, no eval error

- [ ] **Step 7: Commit**

```bash
jj commit -m "feat: dual-stack android 17 guest services and direct boot"
```

### Task 3: In-place Android 17 installer (replace.sh)

**Files:**
- Modify: `initial/replace.sh`
- Test: `shellcheck initial/replace.sh` + `bash -n initial/replace.sh`

**Interfaces:**
- Consumes: Task 2 units (assumes `/dev/vda1` is root)
- Produces: `install_android17()` dispatched when `$VM_LOC/vm_config.json` missing

- [ ] **Step 1: Extend IMG_LOC detection**

Add `elif [ -e /mnt/shared/Download/root_part ] || [ -e /mnt/shared/Download/root_part.zst ]; then IMG_LOC=/mnt/shared/Download` after existing `Download/image` check.

- [ ] **Step 2: Add install_android17()**

Implement per PR #46: `mount -o remount,size=3G /dev/shm`, copy/compress to `/dev/shm/clean_root_part.zst` (`cp` if `.zst`, `zstd -1 -T0` if raw, `gzip -dc | zstd` if `.gz`, else exit 1), `rm -rf $IMG_LOC`, stage `/dev/shm/bin`+`/lib` (`bash zstd dd sync debugfs` + `ld-linux-*` + `ldd` deps), `sysrq=1`, `ld.so --library-path /dev/shm/lib bash -c "zstd -dc | dd of=/dev/vda1 bs=4M conv=fsync + sync + debugfs -w ssv state 1/error_count 0 + sync; echo b > /proc/sysrq-trigger"`.

- [ ] **Step 3: Dispatch on missing vm_config**

Replace `if [ ! -e $STEP_MARKER ]` with `if ! sudo test -e "$VM_LOC/vm_config.json"; then install_android17; elif [ ! -e $STEP_MARKER ]; then step_1; else step_2; fi`.

- [ ] **Step 4: Lint verify**

Run: `bash -n initial/replace.sh && shellcheck initial/replace.sh || true`
Expected: no syntax errors

- [ ] **Step 5: Commit**

```bash
jj commit -m "feat: support android 17 in-place root_part replacement"
```

### Task 4: build_id + virtio-snd hardening

**Files:**
- Modify: `avf/finish.nix`
- Modify: `avf/default.nix` (kernel patch block if needed)
- Test: `tar tzf` inspection + `nix build .#initialImage`

**Interfaces:**
- Consumes: Tasks 2-3 image layout
- Produces: Terminal-parseable `build_id`, confirmed `SND_VIRTIO` module

- [ ] **Step 1: Fix build_id whitespace (issue #40)**

In `avf/finish.nix`, ensure `echo "nixos_avf/.../...-0-$(date)" > build_id` emits single-space, no leading whitespace; document workaround (preserve Debian `build_id_nix`) in code comment. Test: `cat build_id | cat -A` shows no extra spaces.

- [ ] **Step 2: Verify virtio-snd (issue #41)**

Confirm `boot.kernelPatches` `structuredExtraConfig` already sets `SND_VIRTIO=module, SND=yes, SOUND=yes`. If `nix eval` shows missing on unstable kernel, add `SND_VIRTIO` explicitly. No ALSA config change unless `aplay -l` fails on device.

- [ ] **Step 3: Doc typo (PR #44)**

In `README.md`, fix `CROSS_SYSTEM=aarch64_linux` → `aarch64-linux`.

- [ ] **Step 4: Commit**

```bash
jj commit -m "fix: build_id parsing, virtio-snd check, CROSS_SYSTEM docs"
```

### Task 5: Docs, image build, 17-only branch cut

**Files:**
- Modify: `README.md`
- Modify: `initial/README-image.md`
- Create: release notes in `docs/superpowers/specs/` (update)
- Test: human Pixel 10a checklist

**Interfaces:**
- Consumes: Tasks 1-4 working image
- Produces: copy-paste install guide + `android17-only` bookmark plan

- [ ] **Step 1: Rewrite README Android 17 section**

Document: enable Terminal in Dev Options, download `image-unstable-aarch64.tar.gz` from fork releases, place at `/sdcard/linux/nixos.tar.gz` (note `root_part` naming from `install_android17`), launch Terminal auto-install, `Disk resize` 8G+, `sudo nixos-rebuild switch`, `systemctl --failed` check.

- [ ] **Step 2: Build aarch64 image**

Run: `CROSS_SYSTEM=aarch64-linux nix build .#initialImage` (or native if on aarch64)
Expected: `result/*.tar.gz` with `build_id root_part efi_part vm_config.json replace.sh README.md`

- [ ] **Step 3: Cut android17-only bookmark (no push yet)**

Run: `jj bookmark create android17-only` from trunk, plan strip (delete legacy `ttyd` mTLS + `mkService` units + `step_1/step_2`) as follow-up — do not implement here, only list files to delete in README.

- [ ] **Step 4: Commit docs**

```bash
jj commit -m "docs: android 17 install guide for pixel 10a"
```
