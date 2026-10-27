# TabletPad

Старый Android-планшет (4.4+) как графический планшет для Windows.

## 1. Сборка APK
1. Создайте репозиторий на GitHub и загрузите туда содержимое этой папки.
2. Откройте вкладку **Actions**, дождитесь сборки `Build APK` (или запустите вручную).
3. Скачайте артефакт `tabletpad-apk`, внутри `app-debug.apk`.

## 2. Подготовка планшета
- Настройки → О планшете → 7 раз нажмите «Номер сборки».
- Настройки → Для разработчиков → включите **Отладка по USB**.
- Подключите кабель, подтвердите окно «Разрешить отладку».

## 3. Установка
Скачайте [platform-tools](https://developer.android.com/tools/releases/platform-tools) и распакуйте.
```
adb devices
adb install -r app-debug.apk
```
Запустите на планшете приложение **TabletPad**.

## 4. Запуск на ПК
Нужен Python 3.8+ (ставить ничего не надо).
```
python pc\tablet_server.py --mode pen --adb C:\platform-tools\adb.exe
```
Режимы: `mouse`, `pen` (нажим, Windows Ink), `touchpad`.
Другие параметры: `python pc\tablet_server.py -h`.

## Жесты
- Один палец: рисование (mouse/pen) или движение курсора (touchpad)
- Два пальца вверх/вниз: прокрутка
- Тап двумя пальцами: правая кнопка

## По Wi-Fi
В приложении ничего менять не нужно:
`python pc\tablet_server.py --mode pen --host IP_ПЛАНШЕТА`
