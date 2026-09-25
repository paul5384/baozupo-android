# 包租婆出租屋管家 · 安卓版 —— 打包成真正能安装的 APK

这不是网页版，是**原生安卓 App**：装到手机上是一个独立图标，双击直接打开，
不依赖浏览器、不需要联网、数据存在手机本地。

---

## 一、目录里都有什么

```
手机App版/
├── main.py                       ← 程序主逻辑（打包前代码）
├── baozupo.kv                    ← 界面布局（打包前代码）
├── buildozer.spec                ← 打包配置（包名/版本/权限/图标）
├── fonts/simhei.ttf              ← 中文字体（必须带，否则界面全是方框）
├── assets/icon.png               ← 桌面图标
├── assets/presplash.png          ← 启动闪屏
├── .github/workflows/build-apk.yml ← 云端自动打包脚本（方案A用）
├── 本地预览.bat                   ← 电脑上先看效果（Windows）
└── 一键打包APK.sh                ← Linux/WSL 下一条命令打包（方案B用）
```

**`main.py` + `baozupo.kv` 就是「打包前代码」**，这两份是可以直接改的源文件。

---

## 二、先在电脑上看效果（强烈建议）

需要 Python 3.8~3.11（**3.12+ 装 Kivy 比较麻烦，不推荐**）：

```bash
pip install kivy
cd 手机App版
python main.py
```

Windows 用户直接双击 `本地预览.bat` 也行。
会弹出一个 400×760 的手机比例窗口，功能和手机上完全一样，先用这个确认界面没问题再打包。

> 电脑上的数据存在 `C:\Users\你的用户名\.baozupo\baozupo_data.json`，
> 可以用「我的 → 导出备份 / 导入数据」直接吃你电脑版导出的 JSON，先在电脑上把数据灌进去看效果。

---

## 三、正式打包 APK：三种方案，挑一个

> 打包必须在 **Linux** 下做（buildozer 不支持 Windows 直接跑）。
> 所以有三条路，**推荐方案 A**，一条命令都不用敲，还不用装环境。

### 🅰 方案 A：用 GitHub 云端打包（最推荐，全免费）

不用装任何东西，全程在网页上点。

1. 注册 / 登录 <https://github.com>，新建一个仓库（Private 私有仓库也行）。
2. 把 **`手机App版` 文件夹里面的全部内容**（不是文件夹本身）上传到仓库根目录。
   上传办法二选一：
   - 网页操作：仓库页 → `Add file` → `Upload files`，把 `main.py`、`baozupo.kv`、
     `buildozer.spec`、`fonts` 文件夹、`assets` 文件夹、`.github` 文件夹一起拖进去 → Commit。
     （`.github` 是隐藏文件夹，网页上传时如果拖不进去，用下面的 Git 命令方式）
   - Git 命令（推荐，能带上隐藏文件夹）：
     ```bash
     cd 手机App版
     git init
     git add -A
     git commit -m "包租婆安卓版"
     git branch -M main
     git remote add origin https://github.com/你的用户名/你的仓库名.git
     git push -u origin main
     ```
3. 打开仓库页面 → 顶部 **Actions** 标签 → 左边选「**打包安卓APK**」→ 右边
   **Run workflow** → 绿色按钮 **Run workflow**。
4. 等大约 **40 分钟**（第一次要下载 Android SDK/NDK，之后因为有缓存只要几分钟）。
   页面会实时显示进度，`开始打包` 那一步是主要的耗时步骤。
5. 跑完后点进那次运行记录，拉到页面最底部 **Artifacts** → 下载
   **包租婆APK**（是一个 zip，解压出来就是 `.apk`）。
6. 把这个 `.apk` 发到手机（微信文件传输助手 / QQ / 数据线都行），
   手机上点它安装。第一次会提示「未知来源应用」，允许一下即可。

> 免费额度足够：GitHub 私有仓库每月 2000 分钟，本项目一次约 40 分钟（有缓存后 5 分钟）。

---

### 🅱 方案 B：WSL2 / Linux 本机打包

Windows 用户先在「Microsoft Store」装 **Ubuntu**（WSL2），然后：

```bash
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip autoconf libtool \
     pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev cmake libffi-dev libssl-dev
pip3 install buildozer cython

cd /mnt/c/Users/L540/Desktop/python/包租婆/手机App版
buildozer -v android debug
```

出来的 APK 在 `手机App版/bin/` 里。
（本目录里的 `一键打包APK.sh` 就是把上面这些步骤串起来的脚本，`bash 一键打包APK.sh` 即可。）

---

### 🅲 方案 C：Docker（已经装过 Docker 的话最快）

```bash
cd 手机App版
docker run --rm -v "$PWD":/home/user/hostcwd kivy/buildozer buildozer android debug
```

产物同样在 `bin/` 里。

---

## 四、装到手机后怎么用

1. 首次打开先用默认账号 **`admin` / `123456`** 登录，或点「注册新账号」自己建一个。
   （登录界面会提示，登录后可以到「我的 → 修改密码」改掉。）
2. **首页**：10 项实时统计 + 到期提醒 + 快捷操作；顶部可切换统计月份。
3. **房屋**：卡片列表，每张卡上有 `租客 / 收租 / 水电 / 更多` 四个按钮。
   - 右上「＋新增」→ 添加新房，**会自动带入最近一套房的地址、面积、租金、配套**，
     你只改房间号就行；也可以用「已有小区快速带入」下拉，选中小区一键带出配置。
   - 「更多」里有：查看详情、修改房屋、以此为模板新增同款房、设置该租客提醒、一键退租、删除记录。
   - 顶部搜索框支持按房间号 / 地址 / 租客姓名电话搜索，右侧可筛选「全部 / 已租 / 空闲」。
4. **租客**：在租 + 历史全部租客，含到期倒计时。
5. **我的**：导出备份 / 导入数据、修改密码、清空数据、退出登录、关于。

## 五、手机 ↔ 电脑 数据互通

- **手机 → 电脑**：手机「我的 → 导出备份 / 导入数据 → 导出备份到手机存储」，
  文件会存到手机的 **Download** 目录（文件名 `包租婆备份_日期时间.json`）。
  用微信「文件传输助手」把它发到电脑，电脑版点「**恢复数据**」选中它就同步了。
- **电脑 → 手机**：电脑版「**备份数据**」导出 JSON → 传到手机 Download 目录 →
  手机「导入数据 → 从手机存储导入备份」→ 在列表里选那个文件 → 确认覆盖导入。

数据格式两边完全一致，互为备份。

---

## 六、常见问题

**Q：打包报 `Cython` 相关错误？**
把 `pip install buildozer` 换成 `pip install buildozer "cython==0.29.36"` 再打。

**Q：APK 装不上 / 提示「应用未安装」？**
- 手机设置里允许「安装未知来源应用」。
- 如果之前装过不同签名的同包名版本，先卸载旧的。
- 小米/华为等可能需要关掉「MIUI 优化」或允许「安装外部来源应用」。

**Q：界面全是方框（不显示中文）？**
说明字体没打进去。确认 `fonts/simhei.ttf` 存在，且 `buildozer.spec` 里
`source.include_exts` 含 `ttf`、`source.include_patterns` 含 `fonts/*`。

**Q：想改应用名 / 图标 / 版本号？**
- 应用名：`buildozer.spec` 里的 `title`
- 图标：换掉 `assets/icon.png`（建议 512×512 PNG）
- 版本号：`buildozer.spec` 的 `version` 和 `main.py` 顶部的 `VERSION` 一起改

**Q：想减小 APK 体积？**
`buildozer.spec` 里把 `android.archs` 改成只留 `arm64-v8a`（现在的新手机都是 64 位）。
还可以用一个精简版中文字体替换 `fonts/simhei.ttf`。

**Q：导出的备份在手机里找不到？**
用手机自带的「文件管理」进 `Download` 目录找 `包租婆备份_*.json`；
安卓 11 以上首次运行会弹「允许访问文件」的权限框，要点允许。

**Q：数据会丢吗？**
数据在应用私有目录，卸载 App 才会删。换手机 / 刷机 / 卸载前，
先用「导出备份」把 JSON 传到电脑存一份。
