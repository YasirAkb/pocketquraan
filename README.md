# Pocket Quraan

Books and firmware updates for Pocket Quraan readers (Xteink X3/X4).

This repository must stay **public**: the readers download from it without signing in.

## Books

Pocket Quraan readers open this catalog from **Library** on the Home screen, or **Apps → OPDS Library**. Pick a book to download it straight to the SD card.

### Adding a book

1. Open the `books` folder on GitHub and go into a category folder, such as `Hadith` or `Duaa`.
   - To make a new category, create a new folder. On GitHub: **Add file → Upload files**, then type `NewFolder/` in front of the file name.
2. Click **Add file → Upload files**, drop in the `.epub`, and click **Commit changes**.
3. Wait a minute or two. The **Build book catalog** action rebuilds `catalog.xml`, `feeds/` and `covers/`, and the book then appears on the readers.

To remove a book, delete its `.epub` from `books/`.

The title, author, description and cover all come from the EPUB itself. EPUBs only; PDFs won't open on the reader.

Only upload books you're allowed to share. Anything in this repository can be downloaded by anyone.

### Files the action writes (don't edit by hand)

- `catalog.xml`: the start page the readers open.
- `feeds/`: book lists, 20 books per page.
- `covers/`: small black-and-white cover thumbnails.

To rebuild by hand, open **Actions → Build book catalog → Run workflow**.

## Firmware updates

Readers running Pocket Quraan 2.0.0 or later check this repository from **Settings → System → Check for updates**.

### Publishing a new version

1. Click **Releases → Draft a new release**.
2. Create a tag with a **higher** version number than the last one, for example `v2.0.1`. Use three numbers, `major.minor.patch`.
3. Attach the firmware file. It must be named exactly **`firmware.bin`**.
4. Click **Publish release**.

The readers compare the tag with their own version and only offer an update when the tag is newer. Ticking **Set as a pre-release** hides the release from readers unless they've turned on Pre-release in Settings.

Install updates on a **wall charger**, and don't touch the reader until it has restarted.
