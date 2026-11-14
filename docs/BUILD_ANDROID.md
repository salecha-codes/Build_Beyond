# Build and install AgriScan

## Standard development machine

Install Node.js 22 or newer, JDK 17, and Android SDK Platform 35, Build Tools 35.0.0, platform-tools, and command-line tools through Android Studio or the official SDK manager. The checked-in Gradle wrapper pins Gradle 8.11.1 with a distribution checksum. Android Gradle Plugin is 8.9.2, Kotlin is 2.1.20, and the app minimum is Android API 24.

Set `JAVA_HOME` to JDK 17 and `ANDROID_HOME` to the SDK, or put `sdk.dir=/absolute/path/to/android-sdk` in an untracked root `local.properties`. Accept the Android SDK licenses through the official SDK manager. Then, from the repository root, run:

```sh
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest :app:testDebugUnitTest
```

Gradle builds the website from the repository root and packages its output into the APK. The initial build downloads dependencies and requires Internet access. The installed app loads the bundled website locally; no app-server or first-run asset download is required.

## Prepared cloud workspace

This session has a verified workspace-local JDK and SDK. Its helper configures the proxy and Java truststore without putting credentials in the repository:

```sh
/workspace/tools/android-build :app:assembleDebug :app:assembleDebugAndroidTest :app:testDebugUnitTest
/workspace/tools/android-adb devices
```

Those `/workspace/tools` helpers belong to this prepared machine, not a fresh checkout. Their setup and checksum notes are in `/workspace/tools/ANDROID_SETUP.md`. Use the standard wrapper instructions above on another machine.

## Install

Most current phones use ARM64:

```sh
adb install -r android/app/build/outputs/apk/debug/app-arm64-v8a-debug.apk
```

Use `app-armeabi-v7a-debug.apk` for 32-bit Android, `app-x86_64-debug.apk` for an x86_64 emulator, or the larger `app-universal-debug.apk` when the ABI is unknown. All are debug signed. If manually opening the APK on a phone, Android will ask the user to allow installation from that file source.

App package: `com.debuggers.crophealth`. Launcher: `.MainActivity`.

## Android integration tests

Connect a usable device, then run:

```sh
./gradlew :app:connectedDebugAndroidTest
```

Alternatively, install the app APK and `android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk`, then run the checked-in tests directly:

```sh
adb shell am instrument -w -r com.debuggers.crophealth.test/androidx.test.runner.AndroidJUnitRunner
```

The suite has six native integration tests and four Compose UI tests. Test images and marked test observations belong to the test APK; production history is not seeded. See the validation record for actual execution outcomes and software-emulator constraints.

## Updating the model

Export a complete bundle using the ML tools, then synchronize it with checksum and label verification:

```sh
python3 tools/sync_model_bundle.py --help
```

Rebuild the APK after changing assets. Model metadata, label order, decision policy, preprocessing, and model checksum must all describe the same artifact. Validation remains false until independent evaluation supports changing it.
