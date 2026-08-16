SETUP_SCRIPT = r'''
set -eu
ROOT=$1
WORKSPACE=$2
WORKSPACE_MODE=$3
COMMAND=$4
shift 4

mount --make-rprivate /

# The empty chroot skeleton itself is a bind mount remounted read-only.
# This is stronger than chmod(0555): the sandbox UID may own the skeleton
# inode, but cannot chmod a read-only mount back into a writable directory.
mount --bind "$ROOT" "$ROOT"
mount -o remount,bind,ro "$ROOT"

bind_ro_tree() {
    SRC=$1
    DST=$2
    mount --rbind "$SRC" "$DST"
    mount --make-rslave "$DST"
    mount -o remount,bind,ro "$DST"
}

bind_ro_path() {
    SRC=$1
    DST=$2
    mount --bind "$SRC" "$DST"
    mount -o remount,bind,ro "$DST"
}

bind_ro_tree /usr "$ROOT/usr"

while [ "$#" -gt 0 ]; do
    SPEC=$1
    shift
    SRC=${SPEC%%::*}
    DST=${SPEC#*::}
    if [ -d "$SRC" ]; then
        bind_ro_tree "$SRC" "$ROOT$DST"
    else
        bind_ro_path "$SRC" "$ROOT$DST"
    fi
done

mount --bind "$WORKSPACE" "$ROOT$WORKSPACE"
if [ "$WORKSPACE_MODE" = "ro" ]; then
    mount -o remount,bind,ro "$ROOT$WORKSPACE"
else
    mount -o remount,bind,rw "$ROOT$WORKSPACE"
fi

# Verifiers/oracles may need scratch space even when the candidate workspace is
# read-only. Keep it ephemeral and namespace-local rather than host-backed.
mount -t tmpfs -o mode=1777,nosuid,nodev,noexec,size=64m tmpfs "$ROOT/vsh-tmp"

for SRC in /etc/ld.so.cache /etc/ld.so.conf /etc/passwd /etc/group /etc/nsswitch.conf /etc/hosts /etc/resolv.conf; do
    if [ -e "$SRC" ] && [ -e "$ROOT$SRC" ]; then
        bind_ro_path "$SRC" "$ROOT$SRC"
    fi
done

for SRC in /dev/null /dev/urandom /dev/random; do
    if [ -e "$SRC" ] && [ -e "$ROOT$SRC" ]; then
        mount --bind "$SRC" "$ROOT$SRC"
    fi
done

exec chroot "$ROOT" /usr/bin/setpriv \
    --nnp \
    --securebits +noroot,+noroot_locked \
    --bounding-set=-all \
    --inh-caps=-all \
    --ambient-caps=-all \
    /bin/sh -c 'cd "$1" && exec /bin/sh -c "$2"' vsh "$WORKSPACE" "$COMMAND"
'''
