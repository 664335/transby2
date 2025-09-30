import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class CryptoUtils:
    def __init__(self):
        self.key_file = "encryption.key"
        self.salt_file = "salt.bin"
        
    def generate_key_from_password(self, password: str) -> bytes:
        """从密码生成加密密钥"""
        # 生成或加载盐值
        if os.path.exists(self.salt_file):
            with open(self.salt_file, 'rb') as f:
                salt = f.read()
        else:
            salt = os.urandom(16)
            with open(self.salt_file, 'wb') as f:
                f.write(salt)
        
        # 使用PBKDF2生成密钥
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def encrypt_data(self, data: str, password: str) -> str:
        """加密数据"""
        key = self.generate_key_from_password(password)
        fernet = Fernet(key)
        encrypted_data = fernet.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted_data).decode()
    
    def decrypt_data(self, encrypted_data: str, password: str) -> str:
        """解密数据"""
        try:
            key = self.generate_key_from_password(password)
            fernet = Fernet(key)
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_data = fernet.decrypt(encrypted_bytes)
            return decrypted_data.decode()
        except Exception as e:
            raise ValueError(f"解密失败: {str(e)}")
    
    def is_encrypted(self, data: str) -> bool:
        """检查数据是否已加密"""
        try:
            # 检查是否是base64编码且长度合理
            if len(data) < 16:
                return False
            base64.urlsafe_b64decode(data.encode())
            return True
        except:
            return False
