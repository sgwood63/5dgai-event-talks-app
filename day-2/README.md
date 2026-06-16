# Google Drive File Uploader

This Python script uploads local files to Google Drive using the official Google Drive API v3. It handles OAuth 2.0 user authorization locally and automatically saves token credentials for future runs.

## Prerequisites

1. **Python 3.10.7+** is required.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Google Cloud Setup

Before running the script, you need to enable the Drive API and obtain client secrets:

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a Google Cloud project.
3. Enable the **Google Drive API**:
   - Go to **APIs & Services > Library**, search for "Google Drive API", and click **Enable**.
4. Configure the **OAuth Consent Screen**:
   - Go to **APIs & Services > OAuth consent screen**.
   - Select **Internal** (if you are on Google Workspace) or **External** (if using a personal account, and add your email to the Test Users list).
   - Fill in the required fields (App name, Support email, Developer contact).
5. Generate **Credentials**:
   - Go to **APIs & Services > Credentials**.
   - Click **Create Credentials** > **OAuth client ID**.
   - Select **Desktop App** as the Application Type.
   - Enter a name (e.g., "Drive Uploader") and click **Create**.
   - Download the client secrets JSON file.
   - Rename it to `credentials.json` and place it in the same directory as this script.

## Usage

Run the script by passing the path of the file you want to upload:

```bash
python upload_to_drive.py /path/to/local/file.txt
```

### Options

* `--name`: Rename the file when saving to Google Drive.
  ```bash
  python upload_to_drive.py local_file.txt --name "Important Report.txt"
  ```
* `--parent`: Specify a parent folder ID on Google Drive to upload the file into.
  ```bash
  python upload_to_drive.py local_file.txt --parent "folder_id_here"
  ```
* `--credentials`: Path to the OAuth credentials file (defaults to `credentials.json`).
* `--token`: Path to store/load authorization tokens (defaults to `token.json`).

### First-Run Authentication

The first time you run the script, your browser will open to request permission. Select your Google account and grant the requested Google Drive access. A file named `token.json` will be created automatically. Subsequent runs will use `token.json` and run headlessly without browser interaction.
