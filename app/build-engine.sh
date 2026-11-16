#!/bin/sh
# Build the engine for the app: as native libraries for Android and Linux, and as WebAssembly for browsers.
#   app/build-engine.sh [android] [linux] [web]      (all three if none is named)
# Needs: rustup target add aarch64-linux-android armv7-linux-androideabi x86_64-linux-android wasm32-unknown-unknown
#   and, for Android, the NDK (found through android/local.properties, which Flutter writes, or $ANDROID_NDK_HOME).
set -e
cd "$(dirname "$0")/.."
wanted="${*:-android linux web}"

case " $wanted " in *" linux "*)
    cargo build --release -p biblelastic-ffi
    mkdir -p app/linux/engine && cp target/release/libbiblelastic.so app/linux/engine/
    echo "Linux: $(ls -l app/linux/engine/libbiblelastic.so | awk '{print $5}') bytes" ;;
esac

case " $wanted " in *" android "*)
    if [ -z "$ANDROID_NDK_HOME" ]; then
        sdk=$(sed -n 's/^sdk.dir=//p' app/android/local.properties)
        ANDROID_NDK_HOME=$(ls -d "${sdk%/}"/ndk/* | sort -V | tail -1)
    fi
    tools="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin"
    for pair in aarch64-linux-android:arm64-v8a armv7-linux-androideabi:armeabi-v7a x86_64-linux-android:x86_64; do
        target=${pair%%:*}; abi=${pair##*:}
        clang=$target; [ "$target" = armv7-linux-androideabi ] && clang=armv7a-linux-androideabi
        variable=CARGO_TARGET_$(echo "$target" | tr 'a-z-' 'A-Z_')_LINKER
        env "$variable=$tools/${clang}24-clang" cargo build --release -p biblelastic-ffi --target "$target"
        mkdir -p "app/android/app/src/main/jniLibs/$abi" && cp "target/$target/release/libbiblelastic.so" "app/android/app/src/main/jniLibs/$abi/"
        echo "Android $abi: $(ls -l "app/android/app/src/main/jniLibs/$abi/libbiblelastic.so" | awk '{print $5}') bytes"
    done ;;
esac

case " $wanted " in *" web "*)
    web/build.sh > /dev/null
    mkdir -p app/web/engine && cp web/biblelastic.wasm web/biblelastic.js web/engine-worker.js app/web/engine/
    echo "Web: $(ls -l app/web/engine/biblelastic.wasm | awk '{print $5}') bytes" ;;
esac
