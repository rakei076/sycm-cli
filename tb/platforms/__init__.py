"""平台注册表：名字 -> 命令行模块（用到才导入）。新增平台只在这里加一行。"""
PLATFORMS = {   # 顺序就是 tb modules 列表里的顺序
    "sycm": "tb.platforms.sycm.cli",
    "alimama": "tb.platforms.alimama.cli",
    "dmp": "tb.platforms.dmp.cli",
    "qianniu": "tb.platforms.qianniu.cli",
    "voc": "tb.platforms.voc.cli",
}
