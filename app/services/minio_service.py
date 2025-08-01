import io
import asyncio
from datetime import datetime, timedelta, UTC
from typing import List, Optional, Dict, Any
from minio import Minio
from minio.error import S3Error
import structlog
from app.config import settings

logger = structlog.get_logger()


class MinIOService:
    """Service for managing MinIO storage operations"""
    
    def __init__(self):
        self.client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            region=settings.minio_region
        )
        self.bucket_name = settings.minio_bucket_name
        self._ensure_bucket_exists()
        
        logger.info("--- noit-web-research-system MinIO Configuration ---")
        logger.info(f"Endpoint: {settings.minio_endpoint}")
        logger.info(f"Bucket: {self.bucket_name}")
        logger.info("---------------------------------------------")
    
    def _ensure_bucket_exists(self):
        """Ensure the bucket exists, create if not"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created MinIO bucket: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"Error ensuring bucket exists: {e}")
            raise
    
    async def save_research_file(
        self, 
        directory_path: str, 
        filename: str, 
        content: str,
        content_type: str = "text/markdown"
    ) -> str:
        """
        Save research content to MinIO
        
        Args:
            directory_path: Directory path in MinIO
            filename: Name of the file
            content: Content to save
            content_type: MIME type of content
            
        Returns:
            Full path of the saved file
        """
        
        # Ensure directory path doesn't start with /
        directory_path = directory_path.strip('/')
        
        # Create full file path
        if directory_path:
            full_path = f"{directory_path}/{filename}"
        else:
            full_path = filename
        
        try:
            # Convert content to bytes
            content_bytes = content.encode('utf-8')
            content_stream = io.BytesIO(content_bytes)
            
            # Upload to MinIO
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.client.put_object,
                self.bucket_name,
                full_path,
                content_stream,
                len(content_bytes),
                content_type
            )
            
            logger.info(f"Saved file to MinIO: {full_path}")
            return full_path
            
        except S3Error as e:
            logger.error(f"Error saving file to MinIO: {e}")
            raise
    
    async def get_file_content(self, file_path: str) -> Optional[str]:
        """
        Get file content from MinIO
        
        Args:
            file_path: Path to the file in MinIO
            
        Returns:
            File content as string, None if not found
        """
        
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                self.client.get_object,
                self.bucket_name,
                file_path
            )
            
            content = response.read().decode('utf-8')
            response.close()
            response.release_conn()
            
            return content
            
        except S3Error as e:
            if e.code == "NoSuchKey":
                return None
            logger.error(f"Error getting file from MinIO: {e}")
            raise
    
    async def list_directory_files(
        self, 
        directory_path: str, 
        file_extension: str = ".md",
        max_age_days: int = 90
    ) -> List[Dict[str, Any]]:
        """
        List files in a directory with optional filtering
        
        Args:
            directory_path: Directory path to list
            file_extension: Filter by file extension
            max_age_days: Maximum age of files to include
            
        Returns:
            List of file information dictionaries
        """
        
        # Ensure directory path doesn't start with / but ends with /
        directory_path = directory_path.strip('/') + '/'
        
        try:
            objects = await asyncio.get_event_loop().run_in_executor(
                None,
                list,
                self.client.list_objects(
                    self.bucket_name,
                    prefix=directory_path,
                    recursive=True
                )
            )
            
            files = []
            cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
            
            for obj in objects:
                # Skip if it's a directory
                if obj.object_name.endswith('/'):
                    continue
                
                # Filter by extension
                if file_extension and not obj.object_name.endswith(file_extension):
                    continue
                
                # Filter by age
                if obj.last_modified < cutoff_date:
                    continue
                
                files.append({
                    'name': obj.object_name,
                    'size': obj.size,
                    'last_modified': obj.last_modified,
                    'etag': obj.etag
                })
            
            logger.info(f"Found {len(files)} files in directory: {directory_path}")
            return files
            
        except S3Error as e:
            logger.error(f"Error listing directory files: {e}")
            raise
    
    async def list_directory_contents(
        self, 
        directory_path: str,
        max_age_days: int = 90
    ) -> List[str]:
        """
        List all contents (files and folders) in a directory
        
        Args:
            directory_path: Directory path to list
            max_age_days: Maximum age of files to include
            
        Returns:
            List of object names/paths in the directory
        """
        
        # Ensure directory path doesn't start with / but ends with /
        directory_path = directory_path.strip('/') + '/' if directory_path.strip('/') else ''
        
        try:
            logger.info(f"📁 Listing MinIO directory contents: {directory_path}")
            
            objects = await asyncio.get_event_loop().run_in_executor(
                None,
                list,
                self.client.list_objects(
                    self.bucket_name,
                    prefix=directory_path,
                    recursive=True
                )
            )
            
            content_list = []
            cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
            
            for obj in objects:
                # Include both files and directories
                # Filter by age for files (directories don't have meaningful last_modified)
                if not obj.object_name.endswith('/') and obj.last_modified < cutoff_date:
                    continue
                
                content_list.append(obj.object_name)
            
            logger.info(f"📂 Found {len(content_list)} items in directory: {directory_path}")
            return content_list
            
        except S3Error as e:
            logger.error(f"❌ Error listing directory contents: {e}")
            raise
    
    async def get_directory_content_summary(
        self, 
        directory_path: str, 
        max_files: int = 10,
        max_content_length: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Get a summary of content from files in a directory
        
        Args:
            directory_path: Directory path to analyze
            max_files: Maximum number of files to analyze
            max_content_length: Maximum characters per file to read
            
        Returns:
            List of file summaries with content snippets
        """
        
        try:
            files = await self.list_directory_files(directory_path, max_age_days=90)
            files = sorted(files, key=lambda x: x['last_modified'], reverse=True)[:max_files]
            
            summaries = []
            
            for file_info in files:
                content = await self.get_file_content(file_info['name'])
                if content:
                    # Get first part of content for summary
                    content_snippet = content[:max_content_length]
                    if len(content) > max_content_length:
                        content_snippet += "..."
                    
                    summaries.append({
                        'file_path': file_info['name'],
                        'file_size': file_info['size'],
                        'last_modified': file_info['last_modified'],
                        'content_snippet': content_snippet,
                        'full_content_length': len(content)
                    })
            
            return summaries
            
        except Exception as e:
            logger.error(f"Error getting directory content summary: {e}")
            raise
    
    async def delete_file(self, file_path: str) -> bool:
        """
        Delete a file from MinIO
        
        Args:
            file_path: Path to the file to delete
            
        Returns:
            True if successful, False otherwise
        """
        
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.client.remove_object,
                self.bucket_name,
                file_path
            )
            
            logger.info(f"Deleted file from MinIO: {file_path}")
            return True
            
        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.warning(f"File not found for deletion: {file_path}")
                return False
            logger.error(f"Error deleting file from MinIO: {e}")
            raise
    
    async def file_exists(self, file_path: str) -> bool:
        """
        Check if a file exists in MinIO
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file exists, False otherwise
        """
        
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.client.stat_object,
                self.bucket_name,
                file_path
            )
            return True
            
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            logger.error(f"Error checking file existence: {e}")
            raise
    
    def generate_filename(self, base_name: str, task_order: int = None) -> str:
        """
        Generate a standardized filename for research files
        
        Args:
            base_name: Base name for the file
            task_order: Optional task order number
            
        Returns:
            Generated filename
        """
        
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        
        # Clean base name
        clean_base = "".join(c for c in base_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        clean_base = clean_base.replace(' ', '_')
        
        if task_order is not None:
            return f"{timestamp}_task_{task_order:02d}_{clean_base}.md"
        else:
            return f"{timestamp}_{clean_base}.md"


# Global MinIO service instance
minio_service = MinIOService() 