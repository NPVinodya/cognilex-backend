import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()


class CloudflareR2:
    def __init__(self):
        self.account_id = os.getenv("R2_ACCOUNT_ID")
        self.access_key = os.getenv("R2_ACCESS_KEY_ID")
        self.secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
        self.bucket_name = os.getenv("R2_BUCKET_NAME")
        self.public_url = os.getenv("R2_PUBLIC_URL")

        # Cloudflare R2 endpoint
        self.endpoint_url = f"https://{self.account_id}.r2.cloudflarestorage.com"

        # Initialize S3 client (R2 is S3-compatible)
        self.client = boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(signature_version='s3v4'),
            region_name='auto'
        )

    async def upload_file(self, file_obj, file_key: str, content_type: str = "image/jpeg") -> str:
        """
        Upload file to Cloudflare R2

        Args:
            file_obj: File object to upload
            file_key: Path/key in R2 bucket (e.g., "lawyers/123/profile.jpg")
            content_type: MIME type of file

        Returns:
            str: Public URL of uploaded file
        """
        try:
            # Reset file pointer to beginning
            file_obj.seek(0)

            # Upload to R2
            self.client.upload_fileobj(
                file_obj,
                self.bucket_name,
                file_key,
                ExtraArgs={
                    'ContentType': content_type,
                    'ACL': 'public-read'  # Make file publicly accessible
                }
            )

            # Return public URL
            public_url = f"{self.public_url}/{file_key}"
            return public_url

        except ClientError as e:
            raise Exception(f"R2 upload failed: {str(e)}")

    async def delete_file(self, file_key: str) -> bool:
        """
        Delete file from Cloudflare R2

        Args:
            file_key: Path/key in R2 bucket

        Returns:
            bool: True if successful
        """
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=file_key)
            return True
        except ClientError as e:
            print(f"R2 deletion failed: {str(e)}")
            return False

    async def delete_folder(self, prefix: str) -> bool:
        """
        Delete all files in a folder (by prefix)

        Args:
            prefix: Folder prefix (e.g., "lawyers/123/")

        Returns:
            bool: True if successful
        """
        try:
            # List all objects with prefix
            response = self.client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )

            if 'Contents' in response:
                # Delete all objects
                objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
                self.client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={'Objects': objects_to_delete}
                )

            return True
        except ClientError as e:
            print(f"R2 folder deletion failed: {str(e)}")
            return False


# Singleton instance
r2_storage = CloudflareR2()
