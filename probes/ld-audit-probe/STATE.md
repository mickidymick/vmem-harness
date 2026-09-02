# LD_AUDIT probe — state as of 2026-07-28

## The question

Can `LD_AUDIT` replace `LD_PRELOAD` for vmem's allocator interposition, so we can
run **stock** mimalloc and express the vmem changes as loader-level symbol
redirects instead of a source fork?

A main glibc audit contributor says yes, and that the audit interface had
"a bunch of bugs fixed at 2.35+".

## What is settled

**Two distinct jobs.** They were always separate; only the second is in question.

| | job | today | audit design |
|---|---|---|---|
| 1 | make the app use mimalloc at all | `LD_PRELOAD` | `LD_PRELOAD` (unchanged) |
| 2 | make mimalloc's OS memory come from vmem | fork mimalloc source | `LD_AUDIT` symbol redirect |

`lib/libmimalloc-vmem.so` currently does both: it defines `malloc`/`free`/`mmap`
itself and pulls in `libvmem.so` via DT_NEEDED. That fusion is why the current
setup feels like one operation.

**Measured on corsys4 / glibc 2.31** (`tests/prog2.c`: direct malloc, strdup,
asprintf, calloc):

- `LD_PRELOAD` intercepted **4 of 4** allocations
- `LD_AUDIT` intercepted **1 of 4** — only the direct call from `<main>`
- `la_symbind` never reported a `malloc` binding from libc at all
- heaps split: direct alloc at `0x7f04…` (audit ns), strdup at `0x55b0…` (app ns)

**Cause — not a property of the interface.** libc reaches the allocator through
two different relocation types:

```
R_X86_64_GLOB_DAT   malloc, free        <- NOT reported to the auditor on 2.31
R_X86_64_JUMP_SLOT  realloc, calloc     <- reported
R_X86_64_JUMP_SLOT  __tunable_get_val, _dl_find_dso_for_object   <- reported
```

On 2.31 `la_symbind` fires for PLT (`JUMP_SLOT`) bindings only. libc's
`malloc`/`free` are `GLOB_DAT`, so `strdup`/`asprintf` kept the original
allocator. The earlier conclusion that "LD_AUDIT can't replace LD_PRELOAD" was
an artifact of this glibc version, not the design.

**Cross-namespace symbols work.** Verified: preload a stub with no-op defs, let
`la_symbind` rewrite each binding to the real implementation in the audit
namespace. Calls land, and auditor state stays coherent (`tests/stub.c`,
`tests/audit_api.c`, `tests/app.c`).

Sharp edge: **data symbols do NOT bridge.** `la_symbind` is never consulted for
them — the executable gets a copy relocation and its own copy in BSS. Measured:
app kept the stub's `111` while the auditor bumped its own copy to `1000`, no
error. Consequence: a vmem audit ABI must be **functions only**, no exported
`extern` state.

## Where it stopped — RESUME HERE

Built glibc 2.35 in a prefix (`glibc-2.35-install/`, 125 MB, built with the
system gcc 10.2.1; `tests/build_glibc.sh` reproduces it). corsys4 is Debian 11
and there is **no packaged glibc newer than 2.31**, so a prefix build is the
only path short of an OS upgrade.

> **SLIMMED 2026-08-31 (Projects reorg).** The `glibc-2.35-install/` prefix was
> DELETED to save 125 MB — it is fully reproducible with `tests/build_glibc.sh`.
> To resume the probe: re-run `build_glibc.sh`, then the `tests/audit_cov.c`
> measurement below. Probe now lives at `~/Projects/vmem-work/probes/ld-audit-probe/`.

Last thing observed, and it matters:

```
glibc 2.35's own libc.so.6:
  R_X86_64_GLOB_DAT   free, malloc
  R_X86_64_JUMP_SLOT  realloc, calloc
```

**The relocation types are identical to 2.31.** So the reloc layout is not what
changed between versions. The open question is narrower than it looked: does
2.35's `la_symbind` get invoked for **non-PLT (`GLOB_DAT`) relocations**? That
is the single fact everything else depends on.

The test to answer it is written but **never run**: `tests/audit_cov.c`.

```bash
cd tests
P=../glibc-2.35-install
gcc -shared -fPIC -o libaudit_cov.so audit_cov.c
gcc -shared -fPIC -o libpreload_malloc.so preload_malloc.c -ldl
gcc -o prog2 prog2.c -Wl,-z,lazy

# baseline under the NEW loader, for comparison
$P/lib/ld-linux-x86-64.so.2 --library-path $P/lib ./prog2

# the measurement
LD_AUDIT=$PWD/libaudit_cov.so \
  $P/lib/ld-linux-x86-64.so.2 --library-path $P/lib ./prog2
```

Pass criteria:
1. `symbind reported a malloc binding FROM libc: YES`   ← the decisive line
2. intercept count reaches 4, matching `LD_PRELOAD`
3. no heap split between the direct alloc and strdup's

`audit_cov.c` only redirects bindings whose *caller* is in `LM_ID_BASE`. On 2.31
the auditor's own bindings were never reported so recursion was impossible; if
2.35 really did widen coverage, an unguarded auditor would redirect its own
`malloc` into itself and blow the stack. That same namespace guard is what would
replace `disable_vmem_hooks()` in a real vmem auditor — enforced by the loader
instead of a thread-local flag.

## If the test passes

The audit design becomes real, and these follow:

- stock mimalloc, no fork to rebase
- `disable_vmem_hooks()` deletes (~17 sites across vmem.c, dsa.c, vmem_profile.c)
- the internal arena becomes optional — the uffd-vs-mimalloc-lock deadlock class
  is gone, since vmem's allocations resolve against a different libc entirely
- init becomes deterministic: `la_preinit` runs before any constructor, killing
  the `_mi_vmem_active = -1` race in `vmem_bridge.c:38`

Still unresolved regardless of the version question:

- stock mimalloc does its own over-allocate-and-trim, so it `munmap`s sub-ranges
  of a region right after you registered it → needs partial vregion split
- `madvise`/`mprotect` interception becomes mandatory; `MADV_DONTNEED` on a
  MINOR-registered range is exactly the minor-fault source noted at
  `runtime/vmem.c:864-868`
- you'd track mimalloc's OS-layer behavior across versions rather than owning
  the interface
- TLS across namespaces is untested (`_vmem_hooks_disabled` is `__thread`,
  `vmem.c:291`)

## Timing note

The payoff here is maintenance, not chapter content. Against that: a new glibc
under the only working machine, revalidating the benchmark stack on it, and
rewriting the layer everything sits on — while WP reliability is open and the
Phase 5 sweep is blocked. The thing that would change that calculus is if
**per-caller** interposition (redirect `mmap` for mimalloc but not for the MPI
runtime) turns into a measurement worth having — that is close to the masim
attribution problem.
