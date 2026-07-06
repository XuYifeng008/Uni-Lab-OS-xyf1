## 零散信息记录

枪头盒的尺寸是14.16cm*10.52cm

枪头之间单位距离是9.0mm

试管间距是2.18cm

试管架尺寸14.14cm*5.20cm

LC小瓶架尺寸11.56cm*9.23cm

LC小瓶间距1.72cm

大瓶间距5cm

反应器通道距离六边形中心5.93cm

2.02 1.85 左下角枪头的左下坐标，第1个是x，第2个是y

1.50 1.50

1.39 1.04

这俩是左下角第1个位的坐标



## 新建物料类型

物料1：
- 类型：试管架
- 类名：12TubeRack
- 默认 name：12_tube_rack
- 描述：2行6列
- 外形尺寸 size_x/y/z：14.14 cm / 5.20 cm / 10.50 cm
- 最大容量：每个试管的最大容量为10 mL
- 孔位布局：2行6列，相邻孔间距为2.18 cm
- 单孔容量/直径/深度：单孔容量10 mL，直径1.66cm，深度10.50 cm
- deckconfig type：tube_rack
- 是否需要创建函数/别名：否

物料2：

- 类型：试管架
- 类名：30TubeRack
- 默认 name：30_tube_rack
- 描述：5行6列
- 外形尺寸 size_x/y/z：11.56 cm / 9.23 cm / 5.50 cm
- 最大容量：每个试管的最大容量为3 mL
- 孔位布局：5行6列，相邻孔间距为1.72 cm
- 单孔容量/直径/深度：单孔容量3 mL，直径1.23cm，深度5.50 cm
- deckconfig type：tube_rack
- 是否需要创建函数/别名：否

物料3：

- 类型：试管架
- 类名：3TubeRack
- 默认 name：3_tube_rack
- 描述：1行3列
- 外形尺寸 size_x/y/z：16.50 cm / 6.40 cm / 10.00 cm
- 最大容量：每个试管的最大容量为50 mL
- 孔位布局：1行3列，相邻孔间距为5.00 cm
- 单孔容量/直径/深度：单孔容量50 mL，直径4.00 cm，深度10.00 cm
- deckconfig type：tube_rack
- 是否需要创建函数/别名：否



## Deck_Electrochem说明

deck：

\- name：LaiYu_Deck_ElectroChem

\- size_x/y/z：340 / 250 / 160 mm

\- coordinate_system：

  \- origin：top_left

  \- x_axis：right

  \- y_axis：down

  \- z_axis：up

  \- units：mm

\- safety_margins：

  \- x_min：10

  \- x_max：10

  \- y_min：10

  \- y_max：10

  \- z_clearance：20

模块1：

\- id：module_1_tip_rack

\- name：96枪头盒

\- type：96_tip_rack

\- position x/y/z：0 / 0 / 0 mm

\- size x/y/z：134 / 96 / 7 mm

\- grid：8行12列

\- row_labels：A, B, C, D, E, F, G, H

\- column_labels：01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12

\- well_spacing x/y：9 / 9 mm

\- 第一个孔位 A01 坐标：0 / -63.0 / 0 mm

- 孔位H12坐标：99.0 / 0 / 0 mm

\- 单孔 diameter/depth/volume：9 mm / 116 mm / 1000 uL

\- description：标准96孔枪头盒



模块2：

\- id：module_2_12tubes

\- name：12管试管架

\- type：tube_rack

\- position x/y/z：0 / -100 / 0 mm

\- size x/y/z：141.4 / 52.0 / 105.0 mm

\- grid：2行6列

\- row_labels：A, B

\- column_labels：1, 2, 3, 4, 5, 6

\- well_spacing x/y：21.8 / 21.8 mm

\- 第一个孔位 A1 坐标：0 / -132 / 0 mm

- 孔位B6坐标：109 / -110 / 0 mm

\- 单孔 diameter/depth/volume：16.6 mm / 105.0 mm / 10000 uL

\- description：12管试管架，2行6列



模块3：

\- id：module_3_30tubes

\- name：LC_30瓶架

\- type：tube_rack

\- position x/y/z：0 / -214 / 0 mm

\- size x/y/z：115.5 / 93.0 / 30.5 mm

\- grid：5行6列

\- row_labels：A, B, C, D, E

\- column_labels：01, 02, 03, 04, 05, 06

\- well_spacing x/y：17.2 / 17.2 mm

\- 第一个孔位 A01 坐标：15 / -231 / 30.5 mm

- 孔位E06坐标：101 / -162 / 30.5 mm

\- 单孔 diameter/depth/volume：8.2 mm / 25.0 mm / 1500 uL

\- description：LC_30瓶架，禁用A01~A06



模块4：

\- id：module_4_3tubes

\- name：3瓶架

\- type：tube_rack

\- position x/y/z：140 / -182 / 0 mm

\- size x/y/z：166.0 / 61.5 / 105.0 mm

\- grid：1行3列

\- row_labels：A

\- column_labels：01, 02, 03

\- well_spacing x/y：50.0 / 50.0 mm

\- 第一个孔位 A01 坐标：180 / -215 / 10.5 mm

- 孔位A03坐标：280 / -215 / 10.5 mm

\- 单孔 diameter/depth/volume：40.0 mm / 60.0 mm / 50000 uL

\- description：3瓶架



模块5：

（GreenLab电合成仪）
- 模块 id：module_5_GreenLab
- 模块 name：GreenLab电合成仪
- 模块 type：建议 tube_rack（物料上传时使用已有通用容器类型）
- position x/y/z：132.5 / 0 / 0 mm
- size x/y/z：170.0 / 180.0 / 163.0 mm
- 6个加样口：
  - 单孔 diameter/depth/volume：7.0 mm / 90.0 mm / 15000 uL
  - P1 x/y/z：183.0 / -43.0 / 70.0 mm
  - P2 x/y/z：246.0 / -43.0 / 70.0 mm
  - P3 x/y/z：276.5 / -96.5 / 70.0 mm
  - P4 x/y/z：247.0 / -148.5 / 70.0 mm
  - P5 x/y/z：184.5 / -150.0 / 70.0 mm
  - P6 x/y/z：152.5 / -96.5 / 70.0 mm