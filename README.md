# OPV Energy Loss Analyzer

这是一个给课题组内部使用的有机太阳能电池（OPV）能量损失分析工具，用于基于 EQE、FTPS-EQE / sEQE 和 EQE_EL 数据快速计算并导出 E1、E2、E3 三部分能量损失。工具以本地 WebUI 为主要使用方式，适合组内同学进行日常数据检查、组会汇报和论文数据复核。

> 本工具主要用于内部科研分析和数据整理，计算结果应结合原始谱图质量、器件测试条件和人工判断共同使用。

## 在线访问

已部署到 Render：

```text
https://energy-loss.onrender.com/
```

也可以直接打开：[https://energy-loss.onrender.com/](https://energy-loss.onrender.com/)

## 理论基础

OPV 的开路电压损失通常可拆分为三部分：

- **E1**：Shockley-Queisser（SQ）极限下，由带隙 `Eg` 到 SQ 极限开路电压 `Voc,SQ` 的不可避免热力学损失。
- **E2**：辐射复合极限下，由 `Voc,SQ` 到器件辐射极限开路电压 `Voc,rad` 的额外损失。
- **E3**：非辐射复合导致的电压损失，可由电致发光外量子效率 `EQE_EL` 估算。

程序从普通 EQE 估算光学带隙 `Eg`，使用 `normals/SQlimit.txt` 查表得到 `Voc,SQ`；随后将 EQE 与 FTPS-EQE / sEQE 拼接，用黑体光子通量计算 `J0,rad`，从而得到 `Voc,rad`；最后根据 `EQE_EL` 得到非辐射损失 `E3`。

## 公式

### 总能量损失

```text
Eloss = E1 + E2 + E3
```

### E1：SQ 极限损失

```text
E1 = Eg - Voc,SQ
```

其中 `Eg` 为由 EQE 吸收边估算得到的光学带隙，`Voc,SQ` 从 SQ 极限表插值得到。

### E2：辐射复合损失

```text
E2 = Voc,SQ - Voc,rad
```

辐射极限开路电压：

```text
Voc,rad = (kT / q) * ln(Jsc,rad / J0,rad + 1)
```

短路电流密度：

```text
Jsc,rad = q * integral[EQE(lambda) * Phi_sun(lambda) d(lambda)]
```

辐射暗饱和电流密度：

```text
J0,rad = q * integral[EQE_rad(lambda) * Phi_BB(lambda, T) d(lambda)]
```

其中 `EQE_rad(lambda)` 使用普通 EQE 与 FTPS-EQE / sEQE 在长波吸收边拼接得到。

### E3：非辐射复合损失

```text
E3 = - (kT / q) * ln(EQE_EL)
```

`EQE_EL` 默认在计算得到的 `Jsc,rad` 对应电流密度处进行对数插值；也可以在界面中手动输入目标电流密度。

### 可选校验量

当输入实测 `Voc` 时，WebUI 额外输出：

```text
Eg - Voc
Voc,SQ - Voc
E2 + E3
(Voc,SQ - Voc) - (E2 + E3)
```

这些量可用于比较实测电压损失与 E2/E3 分解是否一致。

## 参数含义

| 参数 / 结果 | 含义 | 单位 |
| --- | --- | --- |
| `Eg_eV` | 由 EQE 吸收边估算的光学带隙 | eV |
| `Voc_SQ_V` | SQ 极限开路电压，由 `normals/SQlimit.txt` 查表插值 | V |
| `Voc_rad_V` | 辐射极限开路电压 | V |
| `E1_eV` | `Eg - Voc,SQ` | eV |
| `E2_eV` | `Voc,SQ - Voc,rad` | eV |
| `E3_eV` | 非辐射复合损失，`-kT ln(EQE_EL)` | eV |
| `E_loss_total_eV` | `E1 + E2 + E3` | eV |
| `Jsc_rad_mA_cm2` | 由 EQE 与 AM1.5G 光谱积分得到的辐射极限短路电流密度 | mA cm^-2 |
| `J0_rad_A_m2` | 由辐射 EQE 与黑体光子通量积分得到的辐射暗饱和电流密度 | mA cm^-2 |
| `EQE_EL_at_Jsc` | 指定电流或 `Jsc,rad` 处插值得到的 EQE_EL | 无量纲 |
| `sEQE_scale` | 将 sEQE 缩放到普通 EQE 标度的乘法因子 | 无量纲 |
| `sEQE_switch_nm` | 普通 EQE 切换到 sEQE 的波长 | nm |
| `sEQE_max_nm` | 用于 `J0,rad` 积分的 sEQE 最大波长 | nm |
| `temperature` | 计算温度，界面默认 300 K | K |
| `el_current` | 指定用于提取 EQE_EL 的电流密度；为空时使用 `Jsc,rad` | mA cm^-2 |
| `Voc_input_V` | 用户在界面中输入的实测开路电压，可选 | V |

## 数据格式

程序支持逗号、制表符或空格分隔的数值表格。文件可以有表头；若找不到匹配表头，会默认使用前两列。

### EQE 文件

要求至少两列：

```csv
Wavelength (%),EQE(%)
300,1.83
310,4.71
320,12.68
```

- 第一列：波长，单位 nm。
- 第二列：EQE，可以为 0-1 小数，也可以为百分数。若最大值大于 1，程序会自动除以 100。
- 表头建议包含 `wavelength`、`lambda`、`nm` 和 `eqe` 等关键词。

### FTPS-EQE / sEQE 文件

用于补充长波弱吸收区。第一列既可以是波长 nm，也可以是能量 eV：

```csv
Wavelength (%),EQE(%)
600,84.19341259
610,83.62890412
620,83
```

说明：

- 若第一列数据最大值不超过 10，程序会自动认为第一列为能量 eV，并换算为波长 nm 后参与后续计算。
- 若第一列数据最大值超过 10，程序会按波长 nm 读取。
- WebUI 中该文件为可选；不上传时仅使用普通 EQE 计算 `J0,rad`。
- 若使用 sEQE，程序会在 EQE 红边自动寻找切换波长，并根据重叠区域自动缩放 sEQE。

### EQE_EL 文件

要求至少两列：

```csv
JSC mA/cm2,EQE_EL_%
0.0119875,0
0.0276125,0.001
0.0687433,0.01
```

- 第一列：电流密度，单位 mA cm^-2，必须为正值。
- 第二列：EQE_EL，可以为 0-1 小数，也可以为百分数。若表头包含 `%` 或最大值大于 1.5，程序会自动除以 100。
- 插值时使用 `log(EQE_EL)` 对 `log(J)` 插值，因此用于插值的 EQE_EL 数据点必须为正值。

### 内置标准数据

`normals/` 目录包含计算所需的标准数据：

- `solar_irradiation.txt`：AM1.5G 太阳光谱，单位 W m^-2 nm^-1。
- `SQlimit.txt`：SQ 极限表，包含能量 `Energy_eV` 和对应 `VOC_V`。

## 运行方法

### 本地使用

1. 确认电脑已安装 Python，并已安装 `numpy`、`pandas`、`scipy`。
2. 打开项目文件夹。
3. 运行根目录中的 `webui.py`。
4. 浏览器打开程序显示的本地地址。
5. 在页面中上传数据并点击 `Calculate`。

如果双击 `webui.py` 后窗口一闪而过，通常说明 Python 环境或依赖没有配置好。可先联系项目维护同学检查环境。

### 在线使用

直接访问：

```text
https://energy-loss.onrender.com/
```

Render 免费实例在长时间无人访问后可能会休眠，首次打开可能需要等待几十秒。

### Render 配置

本项目已经包含 Render 部署所需文件：

- `requirements.txt`：Python 依赖列表。
- `render.yaml`：Render Blueprint 配置文件。

当前 Render 配置如下：

```yaml
services:
  - type: web
    name: energy-loss
    runtime: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: python webui.py --host 0.0.0.0
    healthCheckPath: /
```

其中 `startCommand` 只需要写：

```bash
python webui.py --host 0.0.0.0
```

端口由 Render 自动提供，程序会读取环境变量 `PORT`。

## 项目结构

```text
Energy-Loss/
├── energy_loss/
│   ├── __init__.py         # 计算包入口
│   ├── core.py             # 数据读取、插值、积分和 E1/E2/E3 计算核心
│   └── server.py           # 本地 WebUI 后端和 API
├── frontend/
│   ├── index.html          # WebUI 页面结构
│   ├── styles.css          # WebUI 样式
│   └── app.js              # 文件上传、API 调用、结果绘图和 CSV 导出
├── normals/
│   ├── solar_irradiation.txt
│   └── SQlimit.txt
├── EQE.csv                 # 示例普通 EQE 数据
├── sEQE.csv                # 示例 FTPS-EQE / sEQE 数据
├── EQE_EL.csv              # 示例 EQE_EL 数据
├── DESIGN_SPEC.md          # WebUI 设计规范
├── LICENSE                 # MIT 协议
├── render.yaml             # Render 部署配置
├── requirements.txt        # Python 依赖列表
├── webui.py                # WebUI 启动入口
└── README.md
```

## 使用流程

1. 准备测试数据：普通 EQE、FTPS-EQE / sEQE、EQE_EL。
2. 检查单位：波长为 nm，电流密度为 mA cm^-2，EQE 和 EQE_EL 可用百分数或小数。
3. 运行 `webui.py` 并打开本地 WebUI。
4. 上传 EQE 文件、可选 FTPS-EQE / sEQE 文件和 EQE_EL 文件。
5. 设置 `Radiative EQE max (nm)`、`EQE_EL current`、`Temperature` 和可选实测 `Voc`。
6. 点击 `Calculate`。
7. 检查 E1、E2、E3、`Jsc,rad`、`J0,rad` 和 sEQE 拼接信息。
8. 点击 `Save CSV` 导出结果，用于记录、作图或后续汇总。

## 导出结果

WebUI 计算完成后，点击 `Save CSV` 可导出结果。文件名默认为：

```text
energy_loss_results.csv
```

也可以在 `CSV filename prefix` 中自定义前缀，例如输入 `PM6_Y6_device1` 后会导出：

```text
PM6_Y6_device1_results.csv
```

导出的 CSV 为两列：

```csv
parameter,value
Eg_eV,1.4419
E1_eV,0.2650
Voc_SQ_V,1.1768
```

若浏览器支持文件保存接口，会弹出保存位置选择；否则会直接下载到浏览器默认下载目录。

## 常见问题

### 1. 为什么提示目标电流超出 EQE_EL 范围？

默认情况下，程序会在计算得到的 `Jsc,rad` 处提取 `EQE_EL`。如果 EQE_EL 文件的电流范围没有覆盖该值，就会报错。解决方法：

- 补充更宽电流范围的 EQE_EL 测试数据。
- 在 WebUI 的 `EQE_EL current (mA cm^-2)` 中手动输入一个位于数据范围内的电流密度。

### 2. EQE 或 EQE_EL 应该用百分数还是小数？

两者都可以。普通 EQE 最大值大于 1 时会按百分数处理；EQE_EL 表头包含 `%` 或最大值大于 1.5 时会按百分数处理。为了减少歧义，建议表头明确写成 `EQE(%)` 或 `EQE_EL_%`。

### 3. sEQE 一定要上传吗？

不是。sEQE 是可选数据。但如果只使用普通 EQE，长波弱吸收尾可能不够准确，`J0,rad` 和 `Voc,rad` 会受到影响。正式分析建议使用覆盖长波区的 FTPS-EQE / sEQE。

### 4. Eg 自动估算不符合预期怎么办？

自动估算方法会把波长转换为能量，并在 EQE 低能吸收边寻找最大正斜率点。若谱图噪声较大、吸收边异常或样品有明显肩峰，建议先检查 EQE 原始数据质量，并在结果记录中注明该样品的吸收边判断。

### 5. 为什么 EQE_EL 中的 0 会被忽略？

`E3 = -kT ln(EQE_EL)` 需要对正数取对数，且插值采用 `log(EQE_EL)` 对 `log(J)` 插值。因此 EQE_EL 为 0 或负数的数据点不会参与插值。

### 6. 为什么导出的结果中有些值为空？

如果 EQE_EL 文件中没有足够的正值数据点，或者目标电流不在 EQE_EL 测试范围内，`E3_eV` 和 `E_loss_total_eV` 无法计算。请检查 EQE_EL 数据范围，或在界面中手动指定一个有效电流密度。

### 7. WebUI 端口被占用怎么办？

程序会从默认端口 `8765` 开始自动寻找后续可用端口。以启动窗口中显示的实际地址为准。

## 附录

### A. 主要物理常数

| 常数 | 数值 | 单位 |
| --- | --- | --- |
| `q` | `1.602176634e-19` | C |
| `h` | `6.62607015e-34` | J s |
| `c` | `299792458.0` | m s^-1 |
| `kB` | `1.380649e-23` | J K^-1 |

### B. 计算实现要点

- 表格读取由 `energy_loss.core.read_table()` 完成，支持常见分隔符。
- 普通 EQE 由 `load_eqe()` 读取，并自动处理百分数。
- `Eg` 由 `estimate_eg_from_eqe()` 从 EQE 吸收边估算。
- sEQE 缩放由 `scale_seqe_to_eqe()` 根据 EQE/sEQE 重叠区域的中位比例确定。
- `Jsc,rad` 和 `J0,rad` 使用梯形积分 `numpy.trapezoid()`。
- EQE_EL 使用对数-对数插值，适合跨数量级电流扫描。

### C. 示例结果参考

使用根目录示例数据计算，可得到类似结果：

```text
Eg from EQE          : 1.4419 eV
Voc,SQ from SQ table : 1.1768 V
E1 = Eg - Voc,SQ     : 0.2650 eV
Voc,rad from rad EQE : 0.8504 V
E2 = Voc,SQ - Voc,rad: 0.3265 eV
EQE_EL at Jsc        : 3.4054e-04
E3 = -kT ln(EQE_EL)  : 0.2064 eV
E1 + E2 + E3         : 0.7979 eV
Jsc,rad             : 27.6253 mA/cm2
J0,rad              : 1.4298e-12 A/m2
```

### D. 参考

- Shockley, W.; Queisser, H. J. Detailed Balance Limit of Efficiency of p-n Junction Solar Cells.
- Rau, U. Reciprocity relation between photovoltaic quantum efficiency and electroluminescent emission of solar cells.
- Vandewal, K. et al. Open-circuit voltage losses in organic solar cells and related detailed-balance analyses.
