#!/bin/sh
set -eu
# Isolated build of the exact upstream source and PMRS root-turn admission patch.
# The delivered code-mode host is the recorded official 0.160.0 sidecar. Its
# protocol-V1 initialization succeeded; the same-source build encountered a
# missing upstream rusty_v8 150.4.0 sandbox archive (see docs evidence).
# Optional argument 2 supplies that exact official sidecar for a clean rebuild.
# Requires Linux x86_64 C toolchain, pkg-config, OpenSSL development headers and
# the other upstream native build prerequisites. No model inference is performed.
base=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
build_root=${1:?Provide a new or existing isolated native build directory}
sidecar=${2:-"$base/research_studio/native/codex-code-mode-host"}
python3 - "$sidecar" "$base/docs/native-code-mode-source.json" <<'PY'
import hashlib,json,sys
source=json.load(open(sys.argv[2]));actual=hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest()
assert actual==source['source_binary_sha256'], 'Supply the exact verified official code-mode sidecar'
PY
mkdir -p "$build_root/source" "$build_root/cargo" "$build_root/toolchain" "$build_root/target"
export CARGO_HOME="$build_root/cargo"
export RUSTUP_HOME="$build_root/toolchain"
export CARGO_TARGET_DIR="$build_root/target"
export CARGO_INCREMENTAL=0
export CARGO_PROFILE_DEV_DEBUG=0
commit=2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4
archive="$build_root/source/codex-$commit.tar.gz"
if [ ! -f "$archive" ]; then curl --fail --location "https://codeload.github.com/openai/codex/tar.gz/$commit" --output "$archive"; fi
python3 - "$archive" <<'PY'
import hashlib,sys
assert hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest()=='7a9c5090781a917bf53eb7ca0d1cfae56a2230e00c2d670bc8122c810873deed'
PY
if [ ! -d "$build_root/source/codex-$commit" ]; then
 tar -xzf "$archive" -C "$build_root/source"
 (cd "$build_root/source/codex-$commit" && patch -p1 < "$base/docs/native-goal-client.patch")
fi
if [ ! -x "$CARGO_HOME/bin/rustup" ]; then
 curl --proto '=https' --tlsv1.2 --fail --location https://sh.rustup.rs --output "$build_root/rustup-init.sh"
 sh "$build_root/rustup-init.sh" -y --no-modify-path --profile minimal --default-toolchain 1.95.0
fi
(cd "$build_root/source/codex-$commit/codex-rs" && "$CARGO_HOME/bin/cargo" build -p codex-app-server --bin codex-app-server --profile dev-small -j 2) > "$build_root/build.log" 2>&1
mkdir -p "$base/research_studio/native"
cp "$CARGO_TARGET_DIR/dev-small/codex-app-server" "$base/research_studio/native/codex-app-server"
if [ "$sidecar" != "$base/research_studio/native/codex-code-mode-host" ]; then cp "$sidecar" "$base/research_studio/native/codex-code-mode-host"; fi
chmod 755 "$base/research_studio/native/codex-app-server" "$base/research_studio/native/codex-code-mode-host"
cp "$base/docs/native-goal-APACHE-LICENSE" "$base/research_studio/native/LICENSE"
python3 - "$base" <<'PY'
import pathlib,json,hashlib,sys
p=pathlib.Path(sys.argv[1]);m=json.loads((p/'docs/native-goal-source.json').read_text())
m['code_mode_host_origin']=json.loads((p/'docs/native-code-mode-source.json').read_text())
m.update(binary_sha256=hashlib.sha256((p/'research_studio/native/codex-app-server').read_bytes()).hexdigest(),code_mode_host_sha256=hashlib.sha256((p/'research_studio/native/codex-code-mode-host').read_bytes()).hexdigest(),architecture='linux-x86_64',build_profile='dev-small (no debug symbols, no incremental)',research_resource_limits=None)
(p/'research_studio/native/manifest.json').write_text(json.dumps(m,indent=2)+'\n')
PY
