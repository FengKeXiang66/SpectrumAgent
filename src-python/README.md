# 里程碑02源码

不修改或覆盖里程碑01已封版exe、安装器、资源树与VM脚本。

执行测试（不需要安装包）：

```powershell
& E:\AI_Agent\.venv\Scripts\python.exe -m pytest src-python/tests -q
```

数据模型使用Pydantic dataclass；字段与JSON Schema在spectrumagent/data/schema.json。
shape恒为(lines,samples,bands)，未知wavelengths=[]，未知fwhm=null。
运行时读取器/raw选择不作为序列化字段；读取器在metadata中标注值模式和scale。
缩放模式to_numpy显式抛DataError；raw模式为只读DN memmap，保持源dtype（塑料样本为uint16）。
read_region全图属于调用方显式选择，允许；无隐式load()路径。
