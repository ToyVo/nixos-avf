# nixos-avf

Android Virtualization Framework is a new virtualization environment for Android

Among others, it is used to provide the Terminal App starting from Android 15 QPR2

This profile contains the necesarry services and kernel configs to get it running under the Terminal app

The system changes have been taken from https://android.googlesource.com/platform/packages/modules/Virtualization/+/refs/heads/main/build/debian

[ » Chat on Matrix ](https://matrix.to/#/#nixos-avf:mkg20001.io)

# Installation using App

There is now an app that performs the installation steps for you.

Note that currently the guides in the README are out of sync as I'm busy with other things.

[ » App for easier installation ](https://github.com/mkg20001/nixos-avf-image-app/releases)

If you have any problems, feel free to join the Matrix Chat

# Downloading initial image

[ » Download nixos-unstable aarch64 image ](https://github.com/nix-community/nixos-avf/releases/download/nixos-unstable/image-unstable-aarch64.tar.gz)

[ » Other architectures/releases ](https://github.com/nix-community/nixos-avf/releases)

# Building initial image (optional, for development)

> [!IMPORTANT]
> You will need an arm64 image for most phones. To build an arm64 image on a x86_64 system, run `export CROSS_SYSTEM=aarch64-linux` before running nix-build
>
> You will need to either [ » emulate aarch64 ](https://nixos-and-flakes.thiscute.world/development/cross-platform-compilation#compile-through-emulated-system) or add [ » a remote builder ](https://nix.dev/tutorials/nixos/distributed-builds-setup.html#set-up-distributed-builds) that supports aarch64.

Assuming current folder is the root of this repo, build the following: `nix-build initial.nix -A config.system.build.avfImage`

Copy the result file to `/sdcard/linux/images.tar.gz` on your phone.

If the VM fails to start, include `./avf/debug.nix` and view the logs on a debuggable version of Android from the Terminal app (there is no better way currently)

# Enabling the Terminal App

If you don't have enabled the Terminal App already you need to enable it in the Developer Options.

Go to Settings > System > Developer Options > Linux development environment (it's close to USB Debugging in the list)

If you don't have Developer Options enabled [ » read how to do it here ](https://developer.android.com/studio/debug/dev-options)

# Using the image

> [!NOTE]
> This only applies to systems before Android 16 QPR2. Newer versions of the Terminal app resize on-demand.
> 
> After installation of the image you want to expand the disk as you will run into space problems during rebuild otherwise.
>
> You can resize the disk under "Settings (Gear) > Disk resize". We recommend 8 GB or more.

> [!IMPORTANT]
> The image only works on Android 16+. Additionally this has only been tested on Pixels, this may not work with other virtualization Engines from different vendors.

### Android 17 (Pixel 10a, stock, unrooted) — tested path

Android 17 Terminal (`ferrochrome/5100000`) changed the VM contract: it boots the host `vmlinuz` directly with `root=/dev/vda1` (no `efi_part` boot), runs `/sbin/init`, exposes a read-only `cidata` ISO instead of the `internal` VirtioFS share, and expects `ttyd` over a UNIX socket bridged via VSOCK port 7681 plus `linux_vm_manager`. This fork handles both old (15/16) and new (17) Terminals in one image.

1. On your phone: Settings > System > Developer Options > enable **Linux development environment**.
2. Download the fork image: `image-unstable-aarch64.tar.gz` from `https://github.com/ToyVo/nixos-avf/releases` (build from `trunk` on `nixos-unstable`).
3. Copy it to the shared folder the VM scans. Either name works — the installer checks all three:
   - `/sdcard/linux/nixos.tar.gz`, or
   - `/sdcard/linux/images.tar.gz`, or
   - `/sdcard/Download/root_part` / `root_part.zst` (raw or zstd-compressed root partition, advanced).
4. In the Terminal app: Settings (gear) > **Recovery** (or run `scripts/android-clean-vm.sh`) to wipe any previous Debian/NixOS VM, then relaunch Terminal. You should see "Auto installing" and the `nixos-avf.log` appear under `/sdcard/`.
5. After first boot: Settings (gear) > **Disk resize** — 8 GB minimum, 12 GB+ recommended before any `nixos-rebuild`.
6. Verify inside the VM:
   ```sh
   systemctl --failed   # expect 0 failed units
   systemctl status ttyd_uds ttyd_vsock_bridge linux_vm_manager nftables sshd
   sudo nixos-rebuild dry-build && sudo nixos-rebuild switch
   aplay -l             # expect VirtIO SoundCard (issue #41)
   ```
7. If the Terminal app crashes on boot with a date-parse error (issue #40), recover via **Recovery** wipe and preserve the Debian id before replacing: `sudo cp build_id "$VM_LOC/build_id_nix"` (see `initial/replace.sh`).

What changed under the hood: legacy `ttyd` mTLS + `forwarder_guest_launcher`/`storage_balloon_agent`/`shutdown_runner` only run when `/mnt/internal/ca.crt` exists (Android ≤16); on 17 the image uses `ttyd_uds` + `socat` VSOCK bridge + `linux_vm_manager` from `/mnt/cidata`, links `/sbin/init` → `prepare-root`, and the installer streams `root_part` straight to `/dev/vda1` from a RAM-backed `tmpfs` pivot (no root-owned VirtioFS writes). A slim `android17-only` branch that deletes the legacy path is planned once this boots on your 10a.

## Debuggable android

You will need a debuggable android build also known as userdebug (eng build also works)

Place the image under /sdcard/linux/images.tar.gz or use scripts/android-download-vm.sh to download and copy the latest image.

Delete existing VM configuration either via app (Settings > Recovery) or via scripts/android-clean-vm.sh

Restart the terminal app. You should get a popup saying "Auto installing" and the Terminal should automatically use your image.

## Production android build

### Without root

[ » App ](https://github.com/nix-community/nixos-avf-image-app)

### With root

Magisk:

```sh
adb shell "su -c 'rm -rfv /data/data/com.android.virtualization.terminal/{files/nixos.log,files/debian.log,files/linux,vm/nixos,vm/debian}'" # clean
adb shell "su -c 'magisk resetprop ro.debuggable 1; stop; start;'" # enable debuggable
adb shell "su -c 'rm -f /data/media/0/linux/images.tar.gz'"
adb shell "su -c 'wget https://github.com/nix-community/nixos-avf/releases/download/nixos-unstable/image-unstable-aarch64.tar.gz -O /data/media/0/linux/images.tar.gz'"
```

Then launch the terminal app. It should auto-install.

After installation is finished you can revert the changes to ro.debuggable.

# Debugging/Common errors

## "Connection to terminal timed out"

Try restarting the app. Try re-installing the image if that doesn't help.

### With root

Check /data/data/com.android.virtualization.terminal/files/nixos.log

If the log contains `EFI boot manager: Cannot load any image` or is missing any systemd messages like "Started xyz.service..." then the image might be corrupted

Run `adb shell rm -rfv /data/data/com.android.virtualization.terminal/{files/nixos.log,files/debian.log,files/linux,vm/nixos,vm/debian}` to clear up any remnants of previous installs, then install the image again

## Terminal crashes on rebuild or other memory heavy activity

The VM has a 4 GB allocation of memory. This allocation does not represent the RAM the VM can actually physically use, only the maximum amount of memory it will be given from the host system under any condition.

That means while the VM may think it has 4 GB of RAM available, there may not be enough physical memory available on the Phone itself.

If the host memory runs full, the guest will crash.

For rebuilds you can split up the rebuild into evaluation and build+switch. Just run `sudo nixos-rebuild dry-build` and only afterwards `sudo nixos-rebuild switch`. This usually works even on low-memory systems.
