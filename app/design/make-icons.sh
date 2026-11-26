#!/bin/sh
# Make the app's icons, for Android and the web, and logo.png, from icon.svg and logo.svg (drawn with headless Chrome, which draws SVG accurately,
# then made smaller with ImageMagick).   app/design/make-icons.sh
# Needs Google Chrome (or set CHROME) and ImageMagick (magick).
set -e
cd "$(dirname "$0")"
chrome="${CHROME:-$(ls /usr/bin/google-chrome /usr/bin/chromium /usr/bin/chromium-browser 2>/dev/null | head -1)}"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
res=../android/app/src/main/res
background='#77A240' # The middle of the icon's green, for Android's adaptive icon and the web's maskable one

draw() { # draw SVG WIDTH HEIGHT PNG
    "$chrome" --headless=new --disable-gpu --user-data-dir="$work/profile" --hide-scrollbars --default-background-color=00000000 \
        --allow-file-access-from-files --window-size="$2,$3" --screenshot="$4" "file://$(realpath "$1")" 2>/dev/null
}

# The book on its own (icon.svg's <g id="book">), smaller and centred: for icons whose shape the device or browser cuts out itself,
# which must keep within the middle of the square (Android: a circle 66/108 of it across; the web's maskable icons: 80%)
book=$(sed -n '/^  <g id="book">/,/^  <\/g>/p' icon.svg)
foreground() { # foreground SCALE BACKGROUND FILE
    printf '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">\n%s\n<g transform="translate(256 256) scale(%s) translate(-256 -240)">\n%s\n</g></svg>\n' \
        "$([ -n "$2" ] && echo "<rect width=\"512\" height=\"512\" fill=\"$2\"/>")" "$1" "$book" > "$3"
}
foreground 0.60 '' "$work/foreground.svg"
foreground 0.72 "$background" "$work/maskable.svg"

draw icon.svg 512 512 "$work/icon.png"
draw "$work/foreground.svg" 512 512 "$work/foreground.png"
draw "$work/maskable.svg" 512 512 "$work/maskable.png"

# Android: the icon itself (for Android 7 and before), and an adaptive icon (Android 8 and after): the book in front of the green
for pair in mdpi:1 hdpi:1.5 xhdpi:2 xxhdpi:3 xxxhdpi:4; do
    folder=${pair%%:*}; scale=${pair##*:}
    magick "$work/icon.png" -resize "$(echo "48 * $scale / 1" | bc)x" "$res/mipmap-$folder/ic_launcher.png"
    magick "$work/foreground.png" -resize "$(echo "108 * $scale / 1" | bc)x" "$res/mipmap-$folder/ic_launcher_foreground.png"
done
mkdir -p "$res/mipmap-anydpi-v26"
cat > "$res/mipmap-anydpi-v26/ic_launcher.xml" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<!-- Made by app/design/make-icons.sh -->
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background"/>
    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
</adaptive-icon>
EOF
cat > "$res/values/ic_launcher_background.xml" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<!-- Made by app/design/make-icons.sh -->
<resources>
    <color name="ic_launcher_background">$background</color>
</resources>
EOF

# The web
magick "$work/icon.png" -resize 192x ../web/icons/Icon-192.png
cp "$work/icon.png" ../web/icons/Icon-512.png
magick "$work/maskable.png" -resize 192x ../web/icons/Icon-maskable-192.png
cp "$work/maskable.png" ../web/icons/Icon-maskable-512.png
magick "$work/icon.png" -resize 32x ../web/favicon.png

# The logo, with its name (cut to its edges)
draw logo.svg 1400 440 "$work/logo.png"
magick "$work/logo.png" -trim +repage logo.png
echo "Made the icons, and logo.png ($(identify -format '%wx%h' logo.png))"
