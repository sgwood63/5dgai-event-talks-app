import os
import argparse
import mimetypes
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# If modifying these scopes, delete the file token.json.
# Using the drive scope to allow uploading and managing files.
SCOPES = ["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

def get_credentials(credentials_path="credentials.json", token_path="token.json"):
    """Gets valid user credentials from storage or runs the OAuth flow."""
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing access token...")
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"Credentials file '{credentials_path}' not found.\n"
                    "Please download OAuth 2.0 Client ID credentials from the Google Cloud Console "
                    "as a Desktop Application and save them as 'credentials.json'."
                )
            print("Initiating local server OAuth flow to authorize application...")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run
        with open(token_path, "w") as token:
            token.write(creds.to_json())
            print(f"Saved credentials to {token_path}")
            
    return creds

def upload_file(file_path, drive_name=None, parent_folder_id=None, credentials_path="credentials.json", token_path="token.json"):
    """Uploads a local file to Google Drive.

    Args:
        file_path (str): Path to the local file.
        drive_name (str): Custom name on Drive. Defaults to the local file's name.
        parent_folder_id (str): Optional parent folder ID in Google Drive.
        credentials_path (str): Path to credentials.json.
        token_path (str): Path to token.json.
    """
    if not os.path.exists(file_path):
        print(f"Error: Local file '{file_path}' does not exist.")
        return None

    try:
        creds = get_credentials(credentials_path, token_path)
        service = build("drive", "v3", credentials=creds)

        # Detect the mimetype of the file if not explicitly known
        mimetype, _ = mimetypes.guess_type(file_path)
        if not mimetype:
            mimetype = "application/octet-stream"

        file_name = drive_name if drive_name else os.path.basename(file_path)
        
        # Build metadata
        file_metadata = {
            "name": file_name
        }
        if parent_folder_id:
            file_metadata["parents"] = [parent_folder_id]

        print(f"Uploading '{file_path}' as '{file_name}' (MIME type: {mimetype})...")
        
        # Create the media upload object. Set resumable=True for robust uploading.
        media = MediaFileUpload(file_path, mimetype=mimetype, resumable=True)
        
        # Execute the upload request
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink"
        ).execute()

        print("\nUpload Successful!")
        print(f"File Name: {file.get('name')}")
        print(f"File ID  : {file.get('id')}")
        print(f"Link     : {file.get('webViewLink')}")
        return file.get("id")

    except HttpError as error:
        print(f"An API error occurred: {error}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload a file to Google Drive.")
    parser.add_argument("file_path", help="Path to the local file to upload.")
    parser.add_argument("--name", help="Name of the file in Google Drive (defaults to local file name).")
    parser.add_argument("--parent", help="Google Drive folder ID to upload into.")
    parser.add_argument("--credentials", default="credentials.json", help="Path to credentials.json (default: credentials.json).")
    parser.add_argument("--token", default="token.json", help="Path to token.json (default: token.json).")

    args = parser.parse_args()
    upload_file(
        file_path=args.file_path,
        drive_name=args.name,
        parent_folder_id=args.parent,
        credentials_path=args.credentials,
        token_path=args.token
    )
