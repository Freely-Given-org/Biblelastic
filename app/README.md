# The Biblelastic app

A minimal Flutter app, for Android, browsers, and Linux desktops: see [docs/App.md](../docs/App.md).

    app/build-engine.sh                              # The engine as native libraries and as WebAssembly
    cd app
    flutter test
    flutter build web --base-href /app/build/web/    # Then serve the repository's top folder, and open /app/build/web/
    flutter build apk --debug
