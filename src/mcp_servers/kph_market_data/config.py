"""
开盘红平台API配置
"""

# 开盘红平台 API 配置（实时）
KPH_API = {
    "url": "https://apphwshhq.kaipanhong.com/w1/api/index.php",
    "timeout": 10,
    "headers": {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 16; 23127PN0CC Build/BP2A.250605.031.A3)",
        "Host": "apphwshhq.kaipanhong.com",
    },
    "params": {
        "PhoneOSNew": "1",
        "DeviceID": "eae3d4b5dcb6437f",
        "VerSion": "6.1.6",
        "Red": "1",
        "apiv": "w46",
    },
}

# 开盘红平台 API 配置（历史）
KPH_HIS_API = {
    "url": "https://apphis.kaipanhong.com/w1/api/index.php",
    "timeout": 10,
    "headers": {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 16; 23127PN0CC Build/BP2A.250605.031.A3)",
        "Host": "apphis.kaipanhong.com",
    },
    "params": {
        "PhoneOSNew": "1",
        "DeviceID": "eae3d4b5dcb6437f",
        "VerSion": "6.1.6",
        "Red": "1",
        "apiv": "w46",
    },
}