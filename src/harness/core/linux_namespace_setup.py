SETUP_SCRIPT = r'''
set -eu
ROOT=$1
WORKSPACE=$2
WORKSPACE_MODE=$3
MOUNT_COUNT=$4
shift 4

mount --make-rprivate /
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

I=0
while [ "$I" -lt "$MOUNT_COUNT" ]; do
    SPEC=$1
    shift
    SRC=${SPEC%%::*}
    DST=${SPEC#*::}
    if [ -d "$SRC" ]; then
        bind_ro_tree "$SRC" "$ROOT$DST"
    else
        bind_ro_path "$SRC" "$ROOT$DST"
    fi
    I=$((I + 1))
done

mount --bind "$WORKSPACE" "$ROOT$WORKSPACE"
if [ "$WORKSPACE_MODE" = "ro" ]; then
    mount -o remount,bind,ro "$ROOT$WORKSPACE"
else
    mount -o remount,bind,rw "$ROOT$WORKSPACE"
fi

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

if [ "$#" -eq 0 ]; then
    echo "sandbox argv is empty" >&2
    exit 127
fi

# Remaining parameters are executable argv, preserved as separate arguments.
exec chroot "$ROOT" /usr/bin/setpriv \
    --nnp \
    --securebits +noroot,+noroot_locked \
    --bounding-set=-all \
    --inh-caps=-all \
    --ambient-caps=-all \
    /bin/sh -c 'WORKSPACE=$1; shift; cd "$WORKSPACE" && exec "$@"' vsh "$WORKSPACE" "$@"
'''
