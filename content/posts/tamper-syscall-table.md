---
title: "CONFIG_KSU_TAMPER_SYSCALL_TABLE: the only docs are in Kconfig"
date: 2026-10-21
summary: There is no official KernelSU documentation for syscall-table hooking. The authoritative description lives in the fork's kernel/Kconfig help text, and the code says why.
tags: kernelsu, arm64, 4.9, hooking
---

If you go looking for documentation on `CONFIG_KSU_TAMPER_SYSCALL_TABLE`, you will
not find a page. Not on `kernelsu.org`, not in the fork's `docs/`, not in its
`website/`. That is not an oversight — the option is a downstream extension, and
the source file that implements it says so in its own header:

> This file is a downstream extension and NOT affiliated, endorsed by, or
> maintained by the official KernelSU developers.

So the closest thing to documentation is the help text inside `kernel/Kconfig`
itself. That text is short, but it is precise:

```
config KSU_TAMPER_SYSCALL_TABLE
	bool "tamper sys_call_table for sucompat + sys_reboot"
	depends on KSU
	depends on (ARM || ARM64)
	default n
	help
	  Use a high-performance syscall table hijacking method demonstrated on zx2c4's
	  kernel-assisted-superuser. Replaces sys_reboot, sys_execve, sys_newfstatat,
	  sys_faccessat, sys_newfstat_ret.
	  As syscalls are called directly, it avoids indirect branch (blr) overhead and
	  complies with Clang CFI.
	  Verified on 3.0 ~ 7.1. Recommended for 3.0 ~ 4.14.
```

## What it actually does

`CONFIG_KSU_TAMPER_SYSCALL_TABLE=y` does two things at once:

- **sucompat.** It makes `sucompat.c` compile its handlers as `static __always_inline`
  and gives them a caller. Without this config (or `BRANCH_LINK`), the handlers exist
  in the binary but nothing ever calls them, so `su` never resolves to KernelSU.
- **fd channel.** It replaces `sys_reboot`, which is where `KSU_INSTALL_MAGIC` is
  handled. That is the same channel `ksud` uses to talk to the kernel.

That combination is why a build with `CONFIG_KSU=y` and LSM hooks enabled can boot,
report `uid=0` through `sudo`, and still have the manager say *Failed to grant
Root!* — the kernel is there, the userspace channel is not.

## Why it does not need to fight rodata

The table is `const`, and on many Android kernels `CONFIG_DEBUG_ALIGN_RODATA=y`
maps it read-only. The fork does not write to it directly. It maps a writable alias:

```
phys_to_page(__pa(base)) -> vmap(&page, 1, VM_MAP, PAGE_KERNEL)
    -> WRITE_ONCE(slot, hook) -> kick_all_cpus_sync()
    -> vunmap()
```

Which means the option is not blocked by read-only page mapping, only by the
syscall table being reachable at all.

## Picking it over the alternatives

The three hook strategies are mutually exclusive by Kconfig:

| option | depends on | recommended range |
|---|---|---|
| `KSU_TAMPER_SYSCALL_TABLE` | `ARM \|\| ARM64` | 3.0 – 4.14 |
| `KSU_HACK_ARM64_BRANCH_LINK` | `ARM64 && KALLSYMS` | 4.19+ |
| `KSU_KPROBES_KSUD` | `KPROBES && KRETPROBES` | deprecated |

Both `BRANCH_LINK` and `KPROBES_KSUD` carry `depends on !KSU_TAMPER_SYSCALL_TABLE`.
On a 4.9 kernel the Kconfig recommendation and the architectural fit point at the
same option, so that is the one to use — not because it happens to work, but
because it is the path the fork maintains for that kernel generation.

## Verification, not vibes

The things worth checking after booting such a build:

- `/proc/config.gz` shows the option `=y` (the CI injection must *replace* the
  `# ... is not set` line, not append — the later line wins).
- `/proc/kallsyms` contains the hook symbols (`ksu_handle_execveat`, ...).
- `su -c id` returns `uid=0` on a real shell, not just `sudo`.
- The manager stops showing the root warning.
- dmesg shows the unhook of `read`/`newfstat` happening a few seconds after boot.

If the symbols are present but nothing is ever called, the config did not land.
That is the failure mode this option exists to avoid.
