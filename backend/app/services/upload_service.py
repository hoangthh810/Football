from pathlib import Path
import shutil

# --- CẤU HÌNH HẰNG SỐ ---
ALLOWED_EXTENSIONS = [".mp4", ".pdf"]
MAX_FILE_SIZE_MB = 50
CONVERT_MB2B = MAX_FILE_SIZE_MB * 1024 * 1024
DESTINATION_FILE = Path('backend/uploads') 

def validate_file(path: Path):
    if not path.exists() or not path.is_file():
        return {'message': "File không tồn tại hoặc đường dẫn không hợp lệ", 'check': False}
        
    file_extension = path.suffix.lower()
    if file_extension not in ALLOWED_EXTENSIONS:
        return {'message': "Định dạng file không hợp lệ. Chỉ chấp nhận Video (.mp4) hoặc PDF (.pdf)", 'check': False}
        
    file_size_bytes = path.stat().st_size
    if file_size_bytes > CONVERT_MB2B:
        return {'message': f"File quá lớn. Dung lượng tối đa là {MAX_FILE_SIZE_MB}MB", 'check': False}
        
    return {'message': "File hợp lệ", 'check': True}

def save_file_to_destination(source_path: Path, target_dir: Path, new_name: str = None):
    target_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{new_name}{source_path.suffix}" if new_name else source_path.name
    
    destination_path = target_dir / file_name
    
    try:
        shutil.copy2(source_path, destination_path) 
        print(f"Lưu file thành công tại: {destination_path}")
        return destination_path
    except Exception as e:
        print(f"Lỗi khi lưu file: {e}")
        return None

def handle_file(file_path_str):
    path_file = Path(file_path_str)

    result = validate_file(path_file)

    if not result['check']:
        print(f"Thất bại: {result['message']}")
        return
        
    file_extension = path_file.suffix.lower()
    
    if file_extension == ".mp4":
        save_file_to_destination(path_file, DESTINATION_FILE / "videos")
    elif file_extension == ".pdf":
        save_file_to_destination(path_file, DESTINATION_FILE / "pdfs")