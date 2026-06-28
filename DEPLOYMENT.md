# Running Page 本地启动与远程部署指南

## 目录

- [环境要求](#环境要求)
- [本地启动](#本地启动)
  - [1. 安装依赖](#1-安装依赖)
  - [2. 同步运动数据](#2-同步运动数据)
  - [3. 启动开发服务器](#3-启动开发服务器)
  - [4. 生成 SVG 海报](#4-生成-svg-海报)
  - [5. 构建生产版本](#5-构建生产版本)
- [Apple Watch 一键配置](#apple-watch-一键配置)
- [远程部署](#远程部署)
  - [方案一：GitHub Pages（推荐）](#方案一github-pages推荐)
  - [方案二：Vercel](#方案二vercel)
  - [方案三：Cloudflare Pages](#方案三cloudflare-pages)
  - [方案四：Docker 自部署](#方案四docker-自部署)
- [数据同步支持列表](#数据同步支持列表)
- [个性化配置](#个性化配置)
- [常用命令速查](#常用命令速查)
- [数据文件说明](#数据文件说明)

---

## 环境要求

| 工具 | 最低版本 | 安装方式 |
|------|---------|---------|
| Python | 3.12+ | `brew install python` |
| Node.js | 20+ | `brew install node` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pnpm | 8+ | `npm install -g corepack && corepack enable` |
| git | any | `brew install git` |

---

## 本地启动

### 1. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/saymagic/running_page.git --depth=1
cd running_page

# 安装 Python 依赖
uv sync

# 安装 Node.js 依赖
npm install -g corepack && corepack enable
pnpm install
```

### 2. 同步运动数据

根据你的数据来源选择对应的同步命令：

**Apple Health / Apple Watch：**

```bash
# 将 iPhone 导出的 export.zip 放入 apple_health_export/ 目录
# 导出路径：iPhone 健康App > 右上角头像 > 导出所有健康数据
make apple-health

# 仅同步跑步数据
make apple-health APPLE_HEALTH_ARGS=--only-run

# 指定导出路径
make apple-health EXPORT_PATH=/path/to/export
```

**Garmin：**

```bash
# 先生成 secret string
uv run python run_page/get_garmin_secret.py email password
# Garmin 中国区
uv run python run_page/get_garmin_secret.py email password --is-cn

# 同步数据
uv run python run_page/garmin_sync.py <secret_string>
# 中国区
uv run python run_page/garmin_sync.py <secret_string> --is-cn
# 仅跑步
uv run python run_page/garmin_sync.py <secret_string> --only-run
```

**Strava：**

```bash
uv run python run_page/strava_sync.py <client_id> <client_secret> <refresh_token>
```

**Nike Run Club：**

```bash
uv run python run_page/nike_sync.py <nike_refresh_token>
```

**Keep：**

```bash
uv run python run_page/keep_sync.py <mobile> <password> --with-gpx
```

**Coros：**

```bash
uv run python run_page/coros_sync.py <account> <password>
```

**GPX / TCX / FIT 文件：**

```bash
# 将文件放入对应目录：GPX_OUT/、TCX_OUT/、FIT_OUT/
uv run python run_page/gpx_sync.py
uv run python run_page/tcx_sync.py
uv run python run_page/fit_sync.py
```

**Intervals.icu：**

```bash
uv run python run_page/intervals_icu_sync.py <athlete_id> <api_key>
```

### 3. 启动开发服务器

```bash
pnpm dev
# 或
pnpm develop
```

访问 http://localhost:5173 查看效果。

### 4. 生成 SVG 海报

```bash
# GitHub 风格贡献图
uv run python run_page/gen_svg.py --from-db --type github \
  --title "My Running" --athlete "YourName" \
  --output assets/github.svg --use-localtime --min-distance 0.5

# 网格海报（超过 10km 的跑步）
uv run python run_page/gen_svg.py --from-db --type grid \
  --athlete "YourName" --output assets/grid.svg --min-distance 10.0

# 圆形日历
uv run python run_page/gen_svg.py --from-db --type circular --use-localtime

# 人生月历
uv run python run_page/gen_svg.py --from-db --type monthoflife \
  --birth 1990-01 --athlete "YourName" --title "Runner Month of Life"

# 年度总结
uv run python run_page/gen_svg.py --from-db --type year_summary \
  --athlete "YourName"
```

### 5. 构建生产版本

```bash
pnpm build
# 构建产物在 dist/ 目录
```

---

## Apple Watch 一键配置

项目提供了一键配置脚本，自动完成环境检查、依赖安装、数据同步和构建：

```bash
bash scripts/apple_watch_setup.sh
```

脚本执行流程：
1. 检查 Python / uv / git / Node / pnpm 是否就绪
2. 安装 Python 依赖（uv sync）
3. 安装 Node.js 依赖（pnpm install）
4. 检查 `apple_health_export/` 目录中的导出数据
5. 同步 Apple Health 数据
6. 构建并预览

**Apple Health 导出数据准备：**

- **手动导出**：iPhone 健康App > 右上角头像 > 导出所有健康数据 > 传输 export.zip 到项目 `apple_health_export/` 目录
- **浏览器自动化导出**：
  ```bash
  uv run python run_page/apple_health_web_export.py
  # 或带 Apple ID 凭据
  uv run python run_page/apple_health_web_export.py --apple-id you@example.com --password
  ```

**支持的导出格式：**
- `export.zip`（压缩包，会自动解压）
- `export.xml`（解压后的 XML）
- 包含 `export.xml` 的目录
- 支持本地化文件名（如中文的 `导出.xml`）

---

## 远程部署

### 方案一：GitHub Pages（推荐）

**适用场景**：数据通过 GitHub Actions 自动同步，站点托管在 GitHub Pages。

#### 步骤 1：配置 GitHub Actions

编辑 `.github/workflows/run_data_sync.yml`，修改环境变量：

```yaml
env:
  RUN_TYPE: apple_health    # 改为你的数据来源
  ATHLETE: your_name        # 你的名字
  TITLE: My Running Page    # 站点标题
  MIN_GRID_DISTANCE: 10     # Grid 海报最小距离(km)
  TITLE_GRID: Over 10km Runs
  BUILD_GH_PAGES: true      # 启用 GitHub Pages 构建
```

`RUN_TYPE` 可选值：

| 值 | 数据来源 |
|----|---------|
| `apple_health` | Apple Health / Apple Watch |
| `garmin` | Garmin Connect |
| `garmin_cn` | Garmin 中国区 |
| `strava` | Strava |
| `nike` | Nike Run Club |
| `keep` | Keep |
| `coros` | Coros |
| `only_gpx` | GPX 文件 |
| `only_fit` | FIT 文件 |
| `only_tcx` | TCX 文件 |
| `intervals_icu` | Intervals.icu |
| `nike_to_strava` | Nike -> Strava |
| `garmin_to_strava` | Garmin -> Strava |
| `garmin_to_strava_cn` | Garmin CN -> Strava |
| `strava_to_garmin` | Strava -> Garmin |
| `strava_to_garmin_cn` | Strava -> Garmin CN |
| `keep_to_strava_sync` | Keep -> Strava |
| `oppo` | OPPO HeyTap |
| `tulipsport` | Tulipsport |
| `db_updater` | 数据库升级 |

#### 步骤 2：配置 Secrets

在 GitHub 仓库 Settings > Secrets and variables > Actions 中添加对应凭证：

| RUN_TYPE | 需要的 Secrets |
|----------|---------------|
| `apple_health` | `APPLE_HEALTH_EXPORT_PATH`（如 `apple_health_export`） |
| `garmin` | `GARMIN_SECRET_STRING` |
| `garmin_cn` | `GARMIN_SECRET_STRING_CN` |
| `strava` | `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_CLIENT_REFRESH_TOKEN` |
| `nike` | `NIKE_REFRESH_TOKEN` |
| `keep` | `KEEP_MOBILE`, `KEEP_PASSWORD` |
| `coros` | `COROS_ACCOUNT`, `COROS_PASSWORD` |
| `intervals_icu` | `INTERVALS_ICU_ATHLETE_ID`, `INTERVALS_ICU_API_KEY` |

#### 步骤 3：启用 GitHub Pages

1. 仓库 Settings > Pages > Source 选择 **GitHub Actions**
2. Push 到 master 分支，Actions 将自动运行
3. 每日 UTC 0:00 自动同步数据并部署

#### 可选配置

```yaml
# 使用 GitHub Cache 存储数据（Vercel 部署时需要）
SAVE_DATA_IN_GITHUB_CACHE: false

# 生成人生月历 SVG
GENERATE_MONTH_OF_LIFE: true
BIRTHDAY_MONTH: 1990-01    # 你的出生年月

# 保存数据为 Parquet 格式
SAVE_TO_PARQENT: false

# 使用 Cloudflare WARP 绕过网络限制（Garmin 可能需要）
USE_CLOUDFLARE_WARP: false
```

### 方案二：Vercel

**适用场景**：无需 GitHub Pages，直接用 Vercel 托管。

1. Fork 本仓库
2. 在 Vercel 导入该项目，直接部署
3. 修改 `.github/workflows/run_data_sync.yml`：
   ```yaml
   SAVE_DATA_IN_GITHUB_CACHE: true   # 必须！Vercel 不读取仓库数据文件
   BUILD_GH_PAGES: false             # 关闭 GitHub Pages 构建
   ```
4. 数据通过 GitHub Actions 同步后存入 GitHub Cache，Vercel 构建时从 Cache 读取

### 方案三：Cloudflare Pages

1. Fork 本仓库并连接到 Cloudflare Pages
2. 构建配置：
   - Framework preset: `Create React App`
   - Build command: `pnpm build`
   - Build output directory: `dist`
3. 添加环境变量：`PYTHON_VERSION=3.12`
4. 同样需要设置 `SAVE_DATA_IN_GITHUB_CACHE: true`

### 方案四：Docker 自部署

**适用场景**：有自己的服务器，Docker 一键部署。

```bash
# Nike Run Club
docker build -t running_page:latest . \
  --build-arg app=NRC \
  --build-arg nike_refresh_token="YOUR_TOKEN"

# Garmin
docker build -t running_page:latest . \
  --build-arg app=Garmin \
  --build-arg secret_string="YOUR_SECRET"

# Garmin 中国区
docker build -t running_page:latest . \
  --build-arg app=Garmin-CN \
  --build-arg secret_string="YOUR_SECRET"

# Strava
docker build -t running_page:latest . \
  --build-arg app=Strava \
  --build-arg client_id="ID" \
  --build-arg client_secret="SECRET" \
  --build-arg refresh_token="TOKEN"

# Keep
docker build -t running_page:latest . \
  --build-arg app=Keep \
  --build-arg keep_phone_number="PHONE" \
  --build-arg keep_password="PASSWORD" \
  --build-arg YOUR_NAME="YourName"

# 运行
docker run -itd -p 80:80 running_page:latest
```

Dockerfile 采用多阶段构建：
1. `develop-py`：Python 环境 + 依赖
2. `develop-node`：Node.js 环境 + 依赖
3. `data`：执行数据同步 + SVG 生成
4. `frontend-build`：构建前端
5. `web`：Nginx 静态服务

---

## 数据同步支持列表

| 数据来源 | 脚本 | 需要的参数 |
|---------|------|-----------|
| Apple Health | `apple_health_sync.py` | 导出目录路径 |
| Garmin | `garmin_sync.py` | secret_string |
| Garmin CN | `garmin_sync.py --is-cn` | secret_string_cn |
| Strava | `strava_sync.py` | client_id, client_secret, refresh_token |
| Nike | `nike_sync.py` | refresh_token |
| Keep | `keep_sync.py` | mobile, password |
| Coros | `coros_sync.py` | account, password |
| Intervals.icu | `intervals_icu_sync.py` | athlete_id, api_key |
| Komoot | `komoot_sync.py` | email, password |
| GPX 文件 | `gpx_sync.py` | 无（从 GPX_OUT/ 读取） |
| TCX 文件 | `tcx_sync.py` | 无（从 TCX_OUT/ 读取） |
| FIT 文件 | `fit_sync.py` | 无（从 FIT_OUT/ 读取） |
| OPPO | `oppo_sync.py` | id, client_secret, refresh_token |
| Tulipsport | `tulipsport_sync.py` | token |

跨平台同步：

| 方向 | 脚本 |
|-----|------|
| Nike -> Strava | `nike_to_strava_sync.py` |
| Garmin -> Strava | `garmin_to_strava_sync.py` |
| Garmin CN -> Strava | `garmin_to_strava_sync.py --is-cn` |
| Strava -> Garmin | `strava_to_garmin_sync.py` |
| Strava -> Garmin CN | `strava_to_garmin_sync.py --is-cn` |
| Keep -> Strava | `keep_to_strava_sync.py` |
| Garmin CN -> Garmin Global | `garmin_sync_cn_global.py` |

---

## 个性化配置

### 站点信息

编辑 `src/static/site-metadata.ts`：

```typescript
const data = {
  siteTitle: 'Running Page',       // 站点标题
  siteUrl: 'https://run.saymagic.cn',   // 站点 URL
  description: 'Personal site',     // 描述
  logo: 'https://...',              // Logo URL
  navLinks: [                       // 导航链接
    { name: 'Summary', url: '/summary' },
    { name: 'Blog', url: 'https://...' },
  ],
};
```

### 地图与显示

编辑 `src/utils/const.ts`：

```typescript
// 地图服务商：mapcn（免费）/ mapbox / maptiler / stadiamaps
MAP_TILE_VENDOR = 'mapcn';
MAP_TILE_ACCESS_TOKEN = '';         // mapcn 不需要 token

// 样式
IS_CHINESE = true;                  // 中文界面
USE_DASH_LINE = true;               // 虚线路线
LINE_OPACITY = 0.4;                 // 路线透明度
PRIVACY_MODE = false;               // 隐私模式（隐藏地图只显示路线）
LIGHTS_ON = false;                  // 默认开灯
SHOW_ELEVATION_GAIN = false;        // 显示海拔爬升列
RICH_TITLE = false;                 // 丰富活动类型标题
ROAD_LABEL_DISPLAY = true;          // 显示道路标注
```

### 时区

编辑 `run_page/config.py`：

```python
BASE_TIMEZONE = "Asia/Shanghai"  # 改为你的时区
```

---

## 常用命令速查

```bash
# === 依赖安装 ===
uv sync                              # Python 依赖
pnpm install                         # Node.js 依赖

# === 数据同步 ===
make apple-health                    # Apple Health 同步
make apple-health APPLE_HEALTH_ARGS=--only-run  # 仅跑步
uv run python run_page/garmin_sync.py <secret>   # Garmin 同步
uv run python run_page/strava_sync.py <id> <secret> <token>  # Strava 同步

# === SVG 生成 ===
make gen-svg                         # 生成 github + grid 海报

# === 开发 ===
pnpm dev                             # 启动开发服务器
make tui                             # 终端 TUI 界面

# === 构建 ===
pnpm build                           # 生产构建
make ci                              # 完整 CI（test + lint + check + build）

# === 代码质量 ===
make lint                            # ESLint
make check                           # Prettier 检查
make format                          # Prettier 格式化
make test                            # Python 单元测试

# === 数据维护 ===
uv run python run_page/db_updater.py # 数据库升级（添加 elevation gain 字段）
pnpm run data:clean                  # 清除所有数据文件
```

---

## 数据文件说明

| 文件/目录 | 说明 |
|----------|------|
| `run_page/data.db` | SQLite 数据库，存储所有运动记录 |
| `src/static/activities.json` | 前端数据文件，由同步脚本生成 |
| `imported.json` | 已同步记录索引，避免重复导入 |
| `activities/` | 运动数据输出目录 |
| `GPX_OUT/` | GPX 文件输入目录 |
| `TCX_OUT/` | TCX 文件输入目录 |
| `FIT_OUT/` | FIT 文件输入目录 |
| `assets/` | SVG 海报输出目录 |
| `apple_health_export/` | Apple Health 导出数据目录 |
