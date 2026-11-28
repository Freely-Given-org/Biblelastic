#!/bin/sh
# Build a release of the app, with the version from pubspec.yaml, into build/release/VERSION/:
#   - Biblelastic-VERSION-arm64.apk and Biblelastic-VERSION-arm32.apk (for most phones, and for older ones), signed with Freely-Given.org's key
#   - Biblelastic-VERSION.aab, the app bundle to upload to Google Play (with all three Android ABIs), signed with the same key
#   - web/: the web version, for https://Freely-Given.org/Software/Biblelastic/app/ (it gets its modules from ../modules/ there)
#   app/release.sh [android] [play] [web]      (all three if none is named)
# Each upload to Google Play needs a higher build number (the +N after the version in pubspec.yaml) than the last one.
# Needs android/key.properties, with its passwords (see android/app/build.gradle.kts). Publishing what it builds is a separate step: see docs/Publishing.md.
set -e
cd "$(dirname "$0")"
wanted="${*:-android play web}"
version=$(sed -n 's/^version: *\([^+ ]*\).*/\1/p' pubspec.yaml)
out="build/release/$version"
mkdir -p "$out"
defines="--dart-define=APP_VERSION=$version"

case " $wanted " in *" android "*|*" play "*)
    if ! grep -q '^storePassword=.' android/key.properties 2>/dev/null || ! grep -q '^keyPassword=.' android/key.properties; then
        echo "android/key.properties needs its passwords, so that the release is signed with Freely-Given.org's key" >&2; exit 1
    fi
    ./build-engine.sh android ;;
esac

case " $wanted " in *" android "*)
    flutter build apk --release --split-per-abi --target-platform android-arm64,android-arm $defines
    cp build/app/outputs/flutter-apk/app-arm64-v8a-release.apk "$out/Biblelastic-$version-arm64.apk"
    cp build/app/outputs/flutter-apk/app-armeabi-v7a-release.apk "$out/Biblelastic-$version-arm32.apk"
    ls -l "$out"/*.apk ;;
esac

case " $wanted " in *" play "*)
    flutter build appbundle --release $defines
    cp build/app/outputs/bundle/release/app-release.aab "$out/Biblelastic-$version.aab"
    ls -l "$out/Biblelastic-$version.aab" ;;
esac

case " $wanted " in *" web "*)
    ./build-engine.sh web
    # (CanvasKit is served from the site too, rather than from Google's servers)
    flutter build web --release --base-href /Software/Biblelastic/app/ --no-web-resources-cdn --dart-define=MODULES=../modules/ $defines
    rm -rf "$out/web" && cp -r build/web "$out/web"
    du -sh "$out/web" ;;
esac
