# 检查是否正确安装和导入
try:
    import finmind
    print("✓ finmind 导入成功")
    print(f"版本: {finmind.__version__}")
except ImportError as e:
    print(f"✗ 导入失败: {e}")

# 检查模块文件位置
import importlib.util
spec = importlib.util.find_spec("finmind")
if spec:
    print(f"模块位置: {spec.origin}")
else:
    print("未找到 finmind 模块")