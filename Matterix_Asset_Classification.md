# uni-lab-assets 仪器资产 Matterix 三类基类分类

> 依据文档《Uni-Lab 云端 3D 实验室搭建与运行演示文档——改进与细化建议》第 3.2 节，
> 参照 Matterix 框架的三类资产基类，对 `uni-lab-assets-main` 库中全部 478 件仪器资产进行分类。
> 分类依据：URDF/Xacro 中的关节类型（prismatic / revolute / continuous = 关节型）、
> 仪器的物理形态（小型可抓取消耗品 = 刚体）及场景固定性（大型固定仪器 = 静态物体）。

## 总览


| Matterix 基类               | 说明                          | 数量      |
| ------------------------- | --------------------------- | ------- |
| `MatterixArticulationCfg` | 关节型机构（机械臂、液体工作站、旋转/滑动自动化系统） | **82**  |
| `MatterixStaticObjectCfg` | 静态场景物体（固定仪器、家具、货架、机柜）       | **222** |
| `MatterixRigidObjectCfg`  | 刚体可抓取物（耗材、板、管、吸头盒、载架、小型配件）  | **174** |
| **合计**                    |                             | **478** |


## 一、`MatterixArticulationCfg` — 关节型机构

含有 **prismatic / revolute / continuous** 等可驱动关节的仪器，或按功能认定为机器人/液体处理工作站/AGV 的系统。

这类资产在仿真中需要关节状态驱动（JointState），是工作流 Action 的主要执行体。

**共 82 件**


| 品牌/供应商             | 仪器名称                                                      |
| ------------------ | --------------------------------------------------------- |
| Agilent            | Agilent Bravo Liquid Handler                              |
| Applied BioSystems | Applied Biosystems QuantStudio 7 Pro RT-PCR System        |
| BMG LABTECH        | BMG LABTECH PHERAstar FSX Plate Reader                    |
| Beckman Coulter    | Beckman Coulter Biomek i5                                 |
|                    | Beckman Coulter Biomek i7                                 |
| BioTek             | BioTek BioSpa Incubator                                   |
|                    | BioTek Cytation Plate Reader                              |
|                    | BioTek EL311 Plate Reader                                 |
|                    | BioTek EL406 Washer Dispenser                             |
|                    | BioTek ELx405 Select Deepwell Washer                      |
|                    | BioTek Synergy H1 Plate Reader                            |
|                    | BioTek Synergy Neo2 Plate Reader                          |
| Brandel            | Brandel RS-3000 Plate Sealer                              |
| Brooks             | Brooks FluidX IntelliXcap Tube Rack Decapper/Capper       |
| Dispendix          | Dispendix IDot Liquid Handler                             |
| Eppendorf          | Eppendorf Centrifuge 5920R                                |
| Formulatrix        | Formulatrix FAST Liquid Handler                           |
|                    | Formulatrix MANTIS Dispenser with LC3 Carousel (Left)     |
|                    | Formulatrix MANTIS Dispenser with LC3 Carousel (Right)    |
|                    | Formulatrix TEMPEST Liquid Handler                        |
| Hamilton           | Hamilton Entry/Exit Module                                |
|                    | Hamilton LabElite I.D. Capper                             |
|                    | Hamilton Microlab STARplus                                |
|                    | Hamilton Microlab VANTAGE 1.3                             |
|                    | Hamilton Microlab VANTAGE 2                               |
|                    | Hamilton Quad Core Gripper                                |
|                    | Hamilton STAR                                             |
|                    | Hamilton STARlet Liquid Handler                           |
| Hettich            | Hettich Rotanta 460 Robotic                               |
| HighRes Bio        | HighRes AmbiStore D Storage Carousel                      |
|                    | HighRes Bio AmbiStore M                                   |
|                    | HighRes Bio MicroCart                                     |
|                    | HighRes Bio MicroServe Carousel                           |
|                    | HighRes Bio Picoserve                                     |
|                    | HighRes Bio PlateOrient                                   |
|                    | HighRes Bio SteriStore D                                  |
|                    | HighRes Bio SteriStore M                                  |
|                    | HighRes Bio TundraStore D                                 |
|                    | HighRes Bio TundraStore M                                 |
| Integra            | Integra Mini 96                                           |
| Lab Companion      | Lab Companion Microwave Oven                              |
| LiCONiC            | LiCONiC STX110-SA Incubator                               |
|                    | LiCONiC STX220-HRSA Incubator                             |
|                    | LiCONiC STX44-SA                                          |
| Omron              | Omron LD-90                                               |
| OpenTrons          | OpenTrons Flex                                            |
|                    | OpenTrons OT-2 Liquid Handler                             |
| PAA                | PAA CS10 Carousel Stacker                                 |
|                    | PAA KX-2 750 Robot                                        |
|                    | PAA KX-2 Rail (0.5m)                                      |
|                    | PAA KX-2 Rail (1m)                                        |
|                    | PAA KX-2 Rail (2m)                                        |
|                    | PAA KX-660                                                |
| Precise            | Precise 1.0M Rail                                         |
|                    | Precise 1.5M Rail                                         |
|                    | Precise 2.0M Rail                                         |
|                    | Precise PF400 Robot                                       |
|                    | Precise PF750 Robot                                       |
| Sartorius          | Sartorius Intellicyt iQue3                                |
| Tecan              | Tecan EVO 100                                             |
|                    | Tecan EVO 150                                             |
|                    | Tecan EVO 200                                             |
|                    | Tecan EVO 75                                              |
|                    | Tecan EVOlyzer 100                                        |
|                    | Tecan EVOlyzer 150                                        |
|                    | Tecan EVOlyzer 200                                        |
|                    | Tecan Fluent Carousel                                     |
|                    | Tecan Resolvex A200                                       |
|                    | Tecan Uno Single Cell Dispenser                           |
| Thermo Fisher      | Thermo Fisher ALPS 3000 Sealer                            |
|                    | Thermo Fisher Automated Thermal Cycler (ATC)              |
|                    | Thermo Fisher Carousel                                    |
|                    | Thermo Fisher Cytomat 10C (Gate Rear Top Right) Incubator |
|                    | Thermo Fisher Cytomat 2C Incubator                        |
|                    | Thermo Fisher Cytomat SkyLine Storage                     |
|                    | Thermo Fisher IncuCyte S3                                 |
|                    | Thermo Fisher KingFisher Flex Purification System         |
|                    | Thermo Fisher KingFisher Presto Purification System       |
|                    | Thermo Fisher Orbitor BenchTrak                           |
|                    | Thermo Fisher Orbitor RS2 Plate Mover                     |
|                    | Thermo Fisher Spinnaker Robot                             |
| Universal Robots   | Universal Robots UR5e                                     |


## 二、`MatterixStaticObjectCfg` — 静态场景物体

固定在场景中、不被机器人主动抓取的物体，包括分析仪器、离心机、培养箱（无旋转台的单体式）、洗板机、分配器、实验台/货架/机柜、导轨结构件、扫码仪、摄像头等。

这类资产作为碰撞物体（CollisionObject）注册到 MoveIt2 Planning Scene，参与避障规划，但自身不运动。

**共 222 件**


| 品牌/供应商               | 仪器名称                                                                    |
| -------------------- | ----------------------------------------------------------------------- |
| Agilent              | Agilent Bravo Peltier Thermal Station                                   |
|                      | Agilent Bravo Thermal Station                                           |
|                      | Agilent Centrifuge with Loader                                          |
|                      | Agilent Fragment Analyzer                                               |
|                      | Agilent Microplate Barcode Labeler                                      |
|                      | Agilent PlateLoc Sealer                                                 |
|                      | Agilent Tapestation 4150                                                |
|                      | Agilent Tapestation 4200                                                |
| Analytik Jena        | Analytik Jena TRobot II                                                 |
| Applied BioSystems   | Applied Biosystems QuantStudio 7 Flex RT-PCR System                     |
| Artificial           | Artificial Industrial PC Appliance                                      |
|                      | Artificial Plate Hotel                                                  |
|                      | Custom Furniture                                                        |
|                      | Custom Object                                                           |
|                      | Table                                                                   |
|                      | Workbench                                                               |
| BMG LABTECH          | BMG LABTECH CLARIOstar Plus                                             |
|                      | BMG LABTECH FLUOstar Omega                                              |
| Beckman Coulter      | Beckman Coulter 8-Channel Tip Wash ALP                                  |
|                      | Beckman Coulter 96 Channel Tip Wash Station                             |
|                      | Beckman Coulter Echo 525                                                |
|                      | Beckman Coulter Echo 650                                                |
|                      | Beckman Coulter Echo 655                                                |
|                      | Beckman Coulter Echo 65X                                                |
|                      | Beckman Coulter Orbital Shaker ALP                                      |
|                      | Beckman Coulter Shaker ALP                                              |
|                      | Beckman Coulter Trash Bin                                               |
| Benchmark Scientific | Benchmark Scientific Benchmixer V2 Vortexer                             |
|                      | Benchmark Scientific MyFuge 12 Mini Centrifuge                          |
|                      | Benchmark Scientific PlateFuge Microplate Microcentrifuge               |
| BigBear Automation   | Big Bear Automation HT91000 Shaker                                      |
|                      | Big Bear Automation HT91002 Shaker                                      |
|                      | Big Bear Automation HT91100 Shaker                                      |
|                      | Big Bear Automation HT91108 Shaker                                      |
| BioNex               | BioNex HiG3 Centrifuge                                                  |
| BioTek               | BioTek 405 LS Washer                                                    |
|                      | BioTek 405 TS Washer                                                    |
|                      | Biotek Epoch 2 Spectrophotometer                                        |
|                      | BioTek MultiFlo FX Dispenser (MFXP1)                                    |
|                      | BioTek MultiFlo FX Dispenser (MFXP2)                                    |
|                      | BioTek MultiFlo FX Secondary Peri-pump Dispenser                        |
|                      | BioTek MultiFlo FX Strip Washer Module                                  |
|                      | BioTek MultiFlo FX Syringe Module                                       |
| BlueCatBio           | BlueCatBio BlueWasher                                                   |
| Brooks               | Brooks 4titude a4S Sealer                                               |
|                      | Brooks FluidX Perception Rack Reader                                    |
|                      | Brooks FluidX XDC-96 Tube Rack Decapper/Capper                          |
|                      | Brooks XPeel Automated Plate Seal Remover                               |
| Corning              | Corning Falcon 15ml Centrifuge Tube                                     |
|                      | Corning Falcon 50ml Centrifuge Tube                                     |
| Custom               | Custom Chiller Plate Nest                                               |
| Cytena               | Cytena CWASH                                                            |
| Dynamic Devices      | Dynamic Devices Lynx 1200                                               |
|                      | Dynamic Devices Lynx 1800                                               |
|                      | Dynamic Devices Lynx 900                                                |
| Eppendorf            | Eppendorf High-Speed Centrifuge 5430R                                   |
| Formulatrix          | Formulatrix Mantis Base Unit                                            |
| Fritz Gyger          | Fritz Gyger CERTUS FLEX                                                 |
| Generic              | Generic Plate Hotel (Capacity: 10)                                      |
|                      | Table 1.3m Hamilton                                                     |
|                      | Table Ambistore                                                         |
|                      | Table LiCONiC Low Top                                                   |
|                      | Table LiCONiC Tall No Sliders                                           |
|                      | Table LiCONiC Tall With Sliders                                         |
|                      | Table Mobile Cart With Wheels                                           |
|                      | Table PF400                                                             |
| Generic Labware      | Generic Emergency Stop                                                  |
| Hamilton             | Hamilton 15mL Falcon Centrifuge Tube Carrier                            |
|                      | Hamilton 50mL Falcon Centrifuge Tube Carrier                            |
|                      | Hamilton Entry/Exit Chute                                               |
|                      | Hamilton Entry/Exit Stacker                                             |
|                      | Hamilton Heater Shaker Adapter                                          |
|                      | Hamilton Heater Shaker Carrier Base                                     |
|                      | Hamilton MFX 5DWP                                                       |
|                      | Hamilton MFX Heater Shaker Module                                       |
|                      | Hamilton MFX Nunc Heater Shaker Module                                  |
|                      | Hamilton MFX with Heater Shaker                                         |
|                      | Hamilton MFX with Stacker Modules & Heater/Shaker                       |
|                      | Hamilton Star Integration bay                                           |
|                      | Hamilton Teaching Needle Block                                          |
|                      | Hamilton Vantage 1.3M Logistics Cabinet                                 |
|                      | Hamilton Vantage 2.0M Logistics Cabinet                                 |
|                      | Hamilton [MPE]2 Module                                                  |
|                      | Hamilton [MPE]2 Module Base                                             |
| HighRes Bio          | Cellario Host                                                           |
|                      | HighRes Bio 4-position Plate Hotel                                      |
|                      | HighRes Bio Barcode Scanner                                             |
|                      | HighRes Bio Hotel (Capacity: 10)                                        |
|                      | HighRes Bio Hotel (Capacity: 14)                                        |
|                      | HighRes Bio Hotel (Capacity: 19)                                        |
|                      | HighRes Bio Hotel (Capacity: 24)                                        |
|                      | HighRes Bio Hotel (Capacity: 4)                                         |
|                      | HighRes Bio Hotel (Capacity: 5)                                         |
|                      | HighRes Bio Hotel (Capacity: 6)                                         |
|                      | HighRes Bio Hotel (Capacity: 8)                                         |
|                      | HighRes Bio LidValet Delidding Hotel                                    |
|                      | HighRes Bio MicroDock                                                   |
|                      | HighRes Bio MicroServe Hotel                                            |
|                      | HighRes Bio MicroSpin Centrifuge                                        |
|                      | HighRes Bio Nucleus Pod                                                 |
|                      | HighRes Bio Plate Hotel (Capacity: 12)                                  |
|                      | HighRes Bio Plate Hotel (Capacity: 8)                                   |
|                      | HighRes Bio Plate Hotel Nest                                            |
|                      | HighRes Bio PlateWeigh                                                  |
|                      | HighRes Bio Random Access Stacker (Capacity: 12)                        |
| INHECO               | INHECO CPAC Ultraflat HT 2-TEC                                          |
|                      | INHECO ODTC384 - Down                                                   |
|                      | INHECO ODTC96 - Down                                                    |
|                      | INHECO ODTC96 XL Thermal Cycler                                         |
|                      | INHECO Single Plate Incubator/Shaker MP                                 |
|                      | INHECO Teleshake                                                        |
|                      | INHECO Thermoshake AC                                                   |
| Illumia              | Illumia MiSeq Sequencer                                                 |
| Integra              | Integra ASSIST PLUS                                                     |
| Julabo               | Julabo Cooling Hotel                                                    |
| LiCONiC              | LiCONiC STR44 Incubator                                                 |
| Logitech             | Logitech c920 camera                                                    |
| Luminex              | Luminex Flexmap 3D System                                               |
|                      | Luminex Flexmap 3D System Base                                          |
| Memmert              | Memmert Forced Air Incubator                                            |
| Mettler Toledo       | Mettler Toledo Analytical Balance                                       |
| MicroHAWK            | MicroHAWK Barcode Reader on Post                                        |
| Micronic             | Micronic Rack Reader DR505                                              |
| Microscan            | Microscan MS3 Barcode Scanner                                           |
| Microsoft            | Microsoft HoloLens2 Glasses                                             |
| Molecular Devices    | Molecular Devices FLIPR Penta High-Throughput Cellular Screening System |
|                      | Molecular Devices SpectraMax ABS                                        |
|                      | Molecular Devices SpectraMax ABS Plus                                   |
|                      | Molecular Devices SpectraMax i3x                                        |
|                      | Molecular Devices SpectraMax iD3                                        |
|                      | Molecular Devices SpectraMax iD5                                        |
| Nexelcom             | Nexelcom Celigo                                                         |
| OpenTrons            | OpenTrons Heater Shaker Module                                          |
|                      | OpenTrons HEPA Module                                                   |
|                      | OpenTrons Magnetic Module                                               |
|                      | OpenTrons Temperature Module                                            |
|                      | OpenTrons Thermocycler Module                                           |
| OsmoTECH             | OsmoTECH HT Automated Micro-Osmometer                                   |
| PAA                  | PAA Docking Station Unit                                                |
|                      | PAA Sequential Stack SS30SP                                             |
| Perkin Elmer         | Perkin Elmer Opera Phenix                                               |
| Promega              | Promega GloMax Discover Microplate Reader                               |
| Prometheous          | Prometheous Panta                                                       |
| Protein Simple       | Protein Simple Maurice                                                  |
| QInstruments         | QInstruments BioShake 3000-T elm shaker                                 |
|                      | QInstruments BioShake 5000                                              |
|                      | QInstruments BioShake D30-T                                             |
|                      | QInstruments BioShake Q1                                                |
| Retisoft             | Retisoft Plate Hotel                                                    |
| Sartorius            | Sartorius 2L BioReactor Vessel                                          |
|                      | Sartorius Biostat Benchtop Controller                                   |
| Scinomix             | Scinomix SciPrint MP2 Labeler                                           |
| Southern Labware     | Southern Labware Benchtop Incubator Shaker                              |
| Tecan                | Tecan Te-Chrom                                                          |
|                      | Tecan 9 Grid Segment with Cutout                                        |
|                      | Tecan Cabinet extension for Freedom EVO carousel                        |
|                      | Tecan Cabinet for Fluent 1080                                           |
|                      | Tecan Cabinet for Fluent 480                                            |
|                      | Tecan Cabinet for Fluent 780                                            |
|                      | Tecan Cabinet for Freedom Evo 100                                       |
|                      | Tecan D300e Digital Dispenser                                           |
|                      | Tecan Fluent 1080 with extension                                        |
|                      | Tecan Fluent 2 Grid Segment                                             |
|                      | Tecan Fluent 3 Grid Segment                                             |
|                      | Tecan Fluent 4 Nest Hotel                                               |
|                      | Tecan Fluent 480 with extension                                         |
|                      | Tecan Fluent 5 Nest Hotel                                               |
|                      | Tecan Fluent 6 Grid Segment                                             |
|                      | Tecan Fluent 6 Landscape Base Segment                                   |
|                      | Tecan Fluent 6 Nest Shaking Incubator                                   |
|                      | Tecan Fluent 780 with extension                                         |
|                      | Tecan Fluent 8 Grid Segment                                             |
|                      | Tecan Fluent 8 Grid Segment with EVO pins                               |
|                      | Tecan Fluent 9 Nest Hotel                                               |
|                      | Tecan Fluent FCA Thru Deck Waste                                        |
|                      | Tecan Fluent ID left                                                    |
|                      | Tecan Fluent ID middle                                                  |
|                      | Tecan Fluent Lower 6 Grid                                               |
|                      | Tecan Fluent MCA Base Segment                                           |
|                      | Tecan Fluent MCA Thru Deck Waste Chute                                  |
|                      | Tecan Fluent Wash Station with FCA Thru Deck Waste                      |
|                      | Tecan HydroFlex Washer                                                  |
|                      | Tecan Infinite 200 Pro Plate Reader                                     |
|                      | Tecan Infinite F50                                                      |
|                      | Tecan Infinite Lumi Plate Reader                                        |
|                      | Tecan MagicPrep NGS                                                     |
|                      | Tecan MagicPrep NGS Sample Deck                                         |
|                      | Tecan Shelf (large) for Fluent Cabinet                                  |
|                      | Tecan Shelf (small) for Fluent cabinet                                  |
|                      | Tecan Spark Cyto Plate Reader                                           |
|                      | Tecan Spark Plate Reader                                                |
|                      | Tecan Spark Standard Plate Reader                                       |
|                      | Tecan Sunrise Plate Reader                                              |
|                      | Tecan Te-Shake Shaker                                                   |
|                      | Tecan Te-VacS module                                                    |
|                      | Tecan Te-VacS Vacuum                                                    |
| Thermo Fisher        | Table KingFisher Cart                                                   |
|                      | Thermo Fisher ARCTIC A25 Refrigerated Bath Circulator                   |
|                      | Thermo Fisher Cytomat SkyLine Stacker                                   |
|                      | Thermo Fisher Cytomat Stacker (Capacity: 15)                            |
|                      | Thermo Fisher Cytomat Stacker (Capacity: 16)                            |
|                      | Thermo Fisher Cytomat Stacker (Capacity: 21)                            |
|                      | Thermo Fisher Hotel (Capacity: 8)                                       |
|                      | Thermo Fisher Multidrop Combi Dispenser                                 |
|                      | Thermo Fisher NanoDrop One                                              |
|                      | Thermo Fisher Orbitor Hotel                                             |
|                      | Thermo Fisher Orbitor Hotel Mount                                       |
|                      | Thermo Fisher Orbitor Stack                                             |
|                      | Thermo Fisher Plate Hotel (Capacity: 15)                                |
|                      | Thermo Fisher Qubit Flex Fluorometer                                    |
|                      | Thermo Fisher Sorvall Legend Micro 17 Microcentrifuge                   |
|                      | Thermo Fisher Sorvall Legend Micro 17R Microcentrifuge                  |
|                      | Thermo Fisher Stacker                                                   |
|                      | Thermo Fisher Vanquish HPLC                                             |
|                      | Thermo Fisher Varioskan LUX Plate Reader                                |
| Torrey Pines         | Torrey Pines RIC20 Chilling/Heating Dry Bath                            |
| Unchained Labs       | Unchained Labs Big Lunatic Plate Reader                                 |
|                      | Unchained Labs Lunatic/Stunner Plate                                    |
|                      | Unchained Labs Stunner                                                  |
| VWR                  | VWR Microplate Shaker                                                   |
| Waters               | Waters Premier UPLC                                                     |
| Wyatt                | Wyatt Dynapro                                                           |


## 三、`MatterixRigidObjectCfg` — 刚体可抓取物

可被机器人末端执行器抓取和搬运的小型刚体，包括微孔板、PCR 板、离心管、吸头盒、储液槽、管架、载架、巢位适配器、耗材配件等。

每件资产建议定义 `frames`（pre_grasp / grasp / post_grasp / transfer_port）以支持语义操控。

**共 174 件**


| 品牌/供应商          | 仪器名称                                                                |
| --------------- | ------------------------------------------------------------------- |
| Abgene          | Abgene 0.8mL Deepwell Plate                                         |
|                 | Abgene 2.2mL Deepwell Plate                                         |
| Agilent         | Agilent Bravo Magnetic Bead Plate                                   |
|                 | Agilent Bravo Plate Pad                                             |
| Alpaqua         | Alpaqua 96 Well Magnet Plate                                        |
|                 | Alpaqua Magnum FLX                                                  |
|                 | Alpaqua POGO 24 Position Tube Rack                                  |
| Artificial      | Benchling Adapter                                                   |
| Axygen          | Axygen 300mL Reservoir                                              |
| Beckman Coulter | Beckman Coulter Pipette TIps (1000ul)                               |
|                 | Beckman Coulter Pipette Tips (50ul, 190ul)                          |
|                 | Beckman Coulter Plate ALP                                           |
|                 | Beckman Coulter Tip Loader ALP                                      |
| BioRad          | BioRad 384-Well PCR Plate                                           |
|                 | BioRad 96-Well PCR Plate                                            |
|                 | BioRad 96-Well PCR Plate, blue                                      |
|                 | BioRad 96-Well PCR Plate, green                                     |
|                 | BioRad 96-Well PCR Plate, red                                       |
|                 | BioRad 96-Well PCR Plate, yellow                                    |
| Corning         | Corning 384-Well Microplate                                         |
| Custom          | Custom 5ml Tube Rack Adapter                                        |
|                 | Custom Hamilton 2ml Tube Adapter                                    |
|                 | Custom Hamilton 5ml Tube Adapter                                    |
|                 | Custom Handoff Nest                                                 |
| Eppendorf       | Eppendorf 0.5ml Tube                                                |
|                 | Eppendorf 1.5ml Tube                                                |
| FluidX          | FluidX 96-Format 0.26ml 2D-Coded Capped Tube Rack                   |
|                 | FluidX 96-format 1.0ml Tube Rack                                    |
| Generic Labware | Generic 0.5mL Screw Cap Tube                                        |
|                 | Generic 0.5ml Tube Rack                                             |
|                 | Generic 12-well Plate                                               |
|                 | Generic 14x200mm Tube                                               |
|                 | Generic 18x200mm Tube                                               |
|                 | Generic 1ml Tube Rack                                               |
|                 | Generic 24-well Plate                                               |
|                 | Generic 250mL Conical Tube                                          |
|                 | Generic 250mL Erlenmeyer Flask                                      |
|                 | Generic 2ml Screw Cap Tube                                          |
|                 | Generic 5ml Screw Cap Tube                                          |
|                 | Generic 6-well Plate                                                |
|                 | Generic 96-well Microplate (Square Wells)                           |
|                 | Generic 96-well PCR Plate (Round Wells)                             |
|                 | Generic Carboy                                                      |
|                 | Generic Framed Tip Rack                                             |
|                 | Generic Labware 2L Bottle                                           |
|                 | Generic Labware Reagent Bottle                                      |
|                 | Generic Petri Dish                                                  |
|                 | Generic Plate Lid                                                   |
|                 | Generic Reservoir                                                   |
|                 | Generic Tip Box                                                     |
|                 | Generic Tube 10x75                                                  |
|                 | Generic Tube 13x100                                                 |
|                 | Generic Tube 16x125                                                 |
| Hamilton        | Hamilton 0.5mL Tube Carrier (Capacity: 32)                          |
|                 | Hamilton 1.5mL Tube Carrier (Capacity: 32)                          |
|                 | Hamilton 120mL Reagent Trough                                       |
|                 | Hamilton 2-Track Waste                                              |
|                 | Hamilton 200mL Reagent Trough                                       |
|                 | Hamilton 3x120mL Reagent Trough Carrier                             |
|                 | Hamilton 3x200mL Reagent Trough Carrier                             |
|                 | Hamilton 4x200ml Reagent Trough                                     |
|                 | Hamilton 4x200mL Reagent Trough Carrier                             |
|                 | Hamilton 50mL Reagent Trough                                        |
|                 | Hamilton 5x50mL Reagent Trough Carrier                              |
|                 | Hamilton 5x60mL Reagent Trough Carrier                              |
|                 | Hamilton 60mL Reagent Trough                                        |
|                 | Hamilton 96-well Low Magnet Module                                  |
|                 | Hamilton Deepwell Plate Carrier                                     |
|                 | Hamilton Deepwell Reagent Reservoir                                 |
|                 | Hamilton easyCode Carrier                                           |
|                 | Hamilton EasyPick II Carrier                                        |
|                 | Hamilton Framed Tip Rack Carrier                                    |
|                 | Hamilton Low Profile Plate Carrier (Capacity: 5)                    |
|                 | Hamilton MFX Base                                                   |
|                 | Hamilton MFX DWP Module                                             |
|                 | Hamilton MFX Flat High Profile Plate Module                         |
|                 | Hamilton MFX Flat Sloped High Profile Module                        |
|                 | Hamilton MFX HHSF30DWP 3empty                                       |
|                 | Hamilton MFX Low Magnet Module                                      |
|                 | Hamilton MFX Magnet Module                                          |
|                 | Hamilton MFX NTR Flat Module                                        |
|                 | Hamilton MFX with Magnet                                            |
|                 | Hamilton MFX with NTR and Flat HP Plate Modules Preconfigured       |
|                 | Hamilton Microplate Carrier                                         |
|                 | Hamilton Microplate Carrier with Locators                           |
|                 | Hamilton Nested Tip Rack Carrier                                    |
|                 | Hamilton Plate Locator Module                                       |
|                 | Hamilton Sample Tube Carrier (Capacity: 24)                         |
|                 | Hamilton Sample Tube Carrier (Capacity: 32)                         |
|                 | Hamilton Sample Tube Carrier with 0.5mL Tube Adapter (Capacity: 32) |
|                 | Hamilton Sample Tube Carrier with 2ml Tube Adapter (Capacity: 32)   |
|                 | Hamilton Sample Tube Carrier with 5ml Tube Adapter (Capacity: 24)   |
|                 | Hamilton Tip Adapter for 96 Channel Head                            |
|                 | Hamilton Tip Box Carrier (Capacity: 4)                              |
|                 | Hamilton Tube Insert 0.5mL                                          |
|                 | Hamilton Waste Block                                                |
|                 | Nested Tip Rack                                                     |
| HighRes Bio     | HighRes Bio Transfer Nest                                           |
| LiCONiC         | LiCONiC Deepwell Plate Cassette (Capacity: 10)                      |
|                 | LiCONiC Deepwell Plate Cassette (Capacity: 12)                      |
|                 | LiCONiC Deepwell Plate Cassette (Capacity: 7)                       |
|                 | LiCONiC Microplate Cassette (Capacity: 19)                          |
|                 | LiCONiC Microplate Cassette (Capacity: 22)                          |
| Nunc            | Nunc 96-Well Deepwell Plate                                         |
| OpenTrons       | OpenTrons 1.5+2mL Tube Holder Top                                   |
|                 | OpenTrons 15+50mL Tube Holder Top                                   |
|                 | OpenTrons 15mL Tube Holder Top                                      |
|                 | OpenTrons 4-in-1 Tube Rack Set                                      |
|                 | OpenTrons 50mL Tube Holder Top                                      |
|                 | OpenTrons Aluminum Thermal Block 24                                 |
|                 | OpenTrons Aluminum Thermal Block 96                                 |
|                 | OpenTrons Deep Well Adapter                                         |
|                 | OpenTrons Flat Bottom Adapter                                       |
|                 | OpenTrons PCR Adapter                                               |
|                 | OpenTrons Universal Flat Adapter                                    |
| Tecan           | Holder Transfer Tool                                                |
|                 | Tecan Centric Nest                                                  |
|                 | Tecan Eccentric Nest                                                |
|                 | Tecan Fluent 1 Landscape 7mm Nest Segment                           |
|                 | Tecan Fluent 100mL Reagent Trough                                   |
|                 | Tecan Fluent 1x1 1000mL Trough                                      |
|                 | Tecan Fluent 1x10 50mL Eppendorf Tube Runner                        |
|                 | Tecan Fluent 1x16 15mL Eppendorf Tube Runner                        |
|                 | Tecan Fluent 1x16 16mm Tube Runner                                  |
|                 | Tecan Fluent 1x24 1.5mL Eppendorf Tube Runner                       |
|                 | Tecan Fluent 1x24 10mm Tube Runner                                  |
|                 | Tecan Fluent 1x24 13mm Tube Runner                                  |
|                 | Tecan Fluent 1x3 320mL Trough                                       |
|                 | Tecan Fluent 1x32 1.5mL Eppendorf Tube Runner                       |
|                 | Tecan Fluent 1x4 100mL Trough                                       |
|                 | Tecan Fluent 2x4 100mL Trough with waste                            |
|                 | Tecan Fluent 3 Landscape 7mm Nest with Thru Deck Waste Segment      |
|                 | Tecan Fluent 320mL Reagent Trough                                   |
|                 | Tecan Fluent 4 Landscape 61mm Nest Segment                          |
|                 | Tecan Fluent 4 Landscape 61mm Nest Segment with waste               |
|                 | Tecan Fluent 4 Landscape 7mm Nest Segment                           |
|                 | Tecan Fluent 4 Landscape 7mm Nest Segment with waste                |
|                 | Tecan Fluent 4x100mL Reagent Trough Runner                          |
|                 | Tecan Fluent 5 Landscape 61mm Nest Segment                          |
|                 | Tecan Fluent 5 Landscape 7mm Nest Segment                           |
|                 | Tecan Fluent 6 Landscape 61mm Nest Segment                          |
|                 | Tecan Fluent 6 Landscape 7mm Nest Segment                           |
|                 | Tecan Fluent 6 Landscape FCA DiTi Nest Segment                      |
|                 | Tecan Fluent 61mm Nest                                              |
|                 | Tecan Fluent 7mm Nest                                               |
|                 | Tecan Fluent Carousel Cassette (Capacity: 10)                       |
|                 | Tecan Fluent Carousel Cassette (Capacity: 25)                       |
|                 | Tecan Fluent Carousel Cassette (Capacity: 6)                        |
|                 | Tecan Fluent Cool/Heat Nest Segment                                 |
|                 | Tecan Fluent FCA DiTi Nest                                          |
|                 | Tecan Fluent MC 384 Adapter Nest                                    |
|                 | Tecan Fluent MCA 44mm Nest                                          |
|                 | Tecan Fluent MCA Base Segment with 384 DiTi Active Nests (Rear)     |
|                 | Tecan Fluent Reagent Carrier                                        |
|                 | Tecan Fluent Tube Grippers                                          |
|                 | Tecan Freedom EVO 1x3 100mL Trough Runner                           |
|                 | Tecan Freedom EVO 3 Landscape Nest Carrier (fixed to grid pins)     |
|                 | Tecan Freedom EVO 3 Nests for hanging DiTis                         |
|                 | Tecan Freedom EVO DiTi Nest for 1000 µl hanging DiTis               |
|                 | Tecan Freedom EVO DiTi Nest for 200 µl hanging DiTis                |
|                 | Tecan Spacer 29.9mm for Te-Chrom                                    |
|                 | Tecan Te-Shake Nest Adaptor Plate (2 Plates)                        |
|                 | Tecan Te-VacS Plate Park                                            |
|                 | Tecan Te-VacS Spacer No. 2                                          |
|                 | Tecan Tip Box                                                       |
|                 | Tecan Tip Rack                                                      |
|                 | Tecan Tip Rack Base                                                 |
|                 | Tecan Tube runner 1x26 16mm Tubes for Fluent ID                     |
|                 | Tecan Tube runner 1x32 10mm Tubes for Fluent ID                     |
|                 | Tecan Tube runner 1x32 13mm Tubes for Fluent ID                     |
|                 | Tecan Tube runner 1x32 2ml Eppendorf Tubes for Fluent ID            |
| Thermo Fisher   | Thermo Kingfisher 96 Deepwell Magnet Tip Comb                       |
|                 | Thermo KingFisher 96-Well Deepwell Plate                            |
| VP              | VP Scientific SpinVessel 50 mL                                      |


---

## 分类判定说明

### `MatterixArticulationCfg` 判定标准

1. **URDF 有非 fixed 关节**（prismatic/revolute/continuous）→ 直接归入此类
2. **功能为液体处理工作站**（Hamilton STAR/STARlet/STARplus/VANTAGE、Tecan EVO/EVOlyzer、Beckman Coulter Biomek、OpenTrons OT-2/Flex、Dispendix IDot）→ 功能认定为关节型机构
3. **协作机器臂 / AGV**（PAA KX-2/KX-660、Precise PF400/PF750、UR5e、Omron LD-90）→ 关节型机构
4. **带旋转盘/转台的自动化存储系统**（LiCONiC STX、Thermo Cytomat、HighRes AmbiStore、Tecan Carousel）→ 含 continuous 关节

### `MatterixStaticObjectCfg` 判定标准

- 大型固定分析仪器（板式读数仪、测序仪、HPLC、质谱等）
- 独立式离心机（仅机身，无自动装载机械臂）
- 独立式培养箱、振荡器、洗板机（无关节）
- 实验台/机柜/货架/导轨结构件（家具类）
- 机器人系统的配套外设（货架、停靠站、机柜延伸件）

### `MatterixRigidObjectCfg` 判定标准

- 微孔板、PCR 板、深孔板（可被机器人抓取搬运）
- 离心管、Eppendorf 管、Falcon 管等小型容器
- 吸头盒、吸头架、嵌套吸头架
- 试剂槽、储液槽、分液槽
- 载架（Carrier）、巢位（Nest）、适配器（Adapter）等甲板配件
- 卡匣（Cassette）——置于旋转存储柜中的可换板架
- 小型消耗品（试管、烧瓶、培养皿等）

