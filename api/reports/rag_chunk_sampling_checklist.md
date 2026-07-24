# RAG Chunk Sample Review Checklist

Automated summary:

- Resources: 14
- Chunks: 249
- Manual sample size: 30
- Empty text: 0
- Invalid page ranges: 0
- Missing section titles: 249

Manual checks for every item:

- [ ] Semantic unit is complete
- [ ] PDF page range is correct
- [ ] Heading is correct, or mark heading extraction needed
- [ ] Clause number is preserved, or source has no clause number
- [ ] Amount, date, ratio, and period are preserved, or source has none
- [ ] Source type and evidence purpose are correct

## 1. Chunk 1

- Document: 2026年度国家自然科学基金项目申请规定
- Type: guideline / constraint
- Page: 1-1
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 0
- Automatic markers: clause
- Excerpt: 申 请 规 定【**1**】 申 请 规 定 申请人在申请 2026 年度科学基金项目之前，应当认真阅读《国家自然科学基金条 例》（以下简称《条例》）、本《指南》、相关类型项目管理办法、《国家自然科学基 金资助项目资金管理办法》，以及与申请有关的通知、通告等。 现行项目管理办法与 《条例》和本《指南》有冲突的，以《条例》和本《指南》为准。 申请规定包括申请条 件与材料、限项申请规定、预算编报要求、科研诚信和科技伦理要求、依托单位职责和 责任追究等。【**2**】 一、申请条件与材料 （一）申请条件 1. 依托单位的科学技术人员作为申请人申请科学基金项目，应当符合《条例》第 十一条第一款的规定：“（一）具有承担基础研究课题

- [ ] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 1.【**1**】处这里重复读取了申请规定
- 2.【**2**】处应该截断，后续读取了不完整的具体材料内容

## 2. Chunk 30

- Document: 2026年度国家自然科学基金项目申请规定
- Type: guideline / constraint
- Page: 15-15
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 29
- Automatic markers: none
- Excerpt: 【**1**】科研失信行为调查 处理规则》、《国家自然科学基金项目科研不端行为调查处理办法》、《关于对科研领 域相关失信责任主体实施联合惩戒的合作备忘录》、本《指南》的规定以及签署的承 诺，视情节轻重给予相应处理。 2. 申请人及主要参与者违反本《指南》或其他科学技术活动相关要求和承诺的， 一经发现，自然科学基金委将按照《条例》和本《指南》等相关规定，视情节轻重予以 终止评审等相应处理。 3. 对涉嫌违背科研诚信要求或科技伦理规范的学术不端行为，将予以调查，对存 在问题的将严肃处理；对于发现和收到涉及违纪违法的线索和举报，将按照管理权限移 交相关纪检监察部门处理。【**2**】 ·17·

- [ ] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 1.【**1**】这里读取少了书名号《
- 2.【**2**】这里读取了页码，应该去掉

## 3. Chunk 31

- Document: 2026年度国家自然科学基金外国学者研究基金项目指南
- Type: guideline / constraint
- Page: 1-1
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 0
- Automatic markers: clause
- Excerpt: 2026 年度国家自然科学基金外国学者研究基金项目指南 国家自然科学基金外国学者研究基金项目旨在支持自愿来华开展研 究工作的外籍优秀科研人员，在国家自然科学基金资助范围内自主选题， 在中国境内开展基础研究和应用基础研究工作，促进外国学者与中国学者 之间开展长期、稳定的学术合作与交流。 一、项目说明 （一）项目类型 国家自然科学基金外国学者研究基金项目包括以下 3 个层次： 1. 外国青年学者研究基金项目； 2. 外国优秀青年学者研究基金项目； 3. 外国资深学者研究基金项目。 （二）资助领域 数理科学（A）、化学科学（B）、生命科学（C）、地球科学（D）、 工程与材料科学（E）、信息科学(F)

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 正确

## 4. Chunk 38

- Document: 2026年度国家自然科学基金外国学者研究基金项目指南
- Type: guideline / constraint
- Page: 8-8
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 7
- Automatic markers: none
- Excerpt: 国家自然科学基金委员会 国际科研资助部 2026 年 1 月 20 日 附件列表 • Agreement-国家自然科学基金外国学者研究基金项目申报协议书. docx

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 正确，但是这个信息无用，我已经在源文档中删掉

## 5. Chunk 39

- Document: 2026年度可解释可通用的下一代人工智能方法重大研究计划指南
- Type: guideline / constraint
- Page: 1-1
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 0
- Automatic markers: date_or_year
- Excerpt: ⾸ ⻚ 机构概况 策法规 申请资助 国际合作 共享传播 信息公开 专题栏⽬ 项⽬指南 项⽬ 指南 Grants 系 新媒 矩阵 ⼈才 招聘 关于发布可解释、可通⽤的 下⼀代⼈⼯智能⽅法重⼤研究计划 2026年度项⽬指南的通告 国科⾦发计〔2026〕6号 国家⾃然科学基⾦委员会现发布可解释、可通⽤的下⼀代⼈⼯智能⽅法重⼤研究计划2026年度项⽬指南，请申请⼈及依托单 请。 可解释、可通⽤的下⼀代⼈⼯智能⽅法重⼤研究计划2026年度项⽬指南 可解释、可通⽤的下⼀代⼈⼯智能⽅法重⼤研究计划⾯向⼈⼯智能发展国家重⼤战略需求，以⼈⼯智能的基础科学问题为核⼼ 国⼈⼯智能基础研究和⼈才培养，⽀撑我国在新⼀轮

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 正确

## 6. Chunk 47

- Document: 2026年度可解释可通用的下一代人工智能方法重大研究计划指南
- Type: guideline / constraint
- Page: 5-5
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 8
- Automatic markers: clause
- Excerpt: （3）申请书中的资助类别选择“重⼤研究计划”，亚类说明选择“重点⽀持项⽬”或“集成项⽬”，附注说明选择“可解释、可 码选择T01，根据申请的具体研究内容选择不超过5个申请代码。 重点⽀持项⽬的合作研究单位不得超过2个，集成项⽬合作研究单位不得超过4个。 集成项⽬主要参与者必须是项⽬的实际贡献 （4）申请⼈在申请书起始部分应明确说明申请符合本项⽬指南中的资助研究⽅向，以及对解决本重⼤研究计划核⼼科学问题 献。 如果申请⼈已经承担与本重⼤研究计划相关的其他科技计划项⽬，应当在申请书正⽂的“研究基础与⼯作条件”部分论述申请 2. 依托单位应当按照要求完成依托单位承诺、组织申请以及审核申请材料等⼯作。

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 正确

## 7. Chunk 48

- Document: 2026年度面向人机物融合的智能化软件基础研究重大研究计划指南
- Type: guideline / constraint
- Page: 1-1
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 0
- Automatic markers: date_or_year
- Excerpt: 项⽬指南 关于发布⾯向⼈机物融合的智能化软件 基础研究重⼤研究计划2026年度项⽬指南的通告 国科⾦发计〔2026〕17号 国家⾃然科学基⾦委员会现发布⾯向⼈机物融合的智能化软件基础研究重⼤研究计划2026年度项⽬指南，请申请⼈及依托单 请。 ⾯向⼈机物融合的智能化软件基础研究 重⼤研究计划2026年度项⽬指南 “⾯向⼈机物融合的智能化软件基础研究”重⼤研究计划针对关键软件⾃主创新的国家重⼤战略需求，围绕智能化软件新范型的 量保障等⽅⾯的重⼤科学问题，通过信息、数学、物理、⼯程、管理等学科的交叉融合研究，为我国实现关键软件领域的科学突 撑。 ⼀、科学⽬标

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 正确

## 8. Chunk 59

- Document: 2026年度面向人机物融合的智能化软件基础研究重大研究计划指南
- Type: guideline / constraint
- Page: 6-6
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 11
- Automatic markers: clause
- Excerpt: （1）为实现重⼤研究计划总体科学⽬标和多学科集成，获得资助的项⽬负责⼈应当承诺遵守相关数据和资料管理与共享的规定 究计划其他项⽬之间的相互⽀撑关系。 （2）为加强项⽬的学术交流，促进项⽬群的形成和多学科交叉与集成，本重⼤研究计划将每年举办1次资助项⽬的年度学术交流 术研讨会。 获资助项⽬负责⼈有义务参加本重⼤研究计划指导专家组和管理⼯作组所组织的上述学术交流活动，并认真开展学术交 （四）咨询⽅式。 国家⾃然科学基⾦委员会交叉科学部交叉科学四处 联系电话：010-62328922

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 正确

## 9. Chunk 60

- Document: 关于2026年度国家自然科学基金项目申请与结题等有关事项的通告
- Type: call_snapshot / constraint
- Page: 1-1
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 0
- Automatic markers: date_or_year
- Excerpt: 项⽬指南 关于2026年度国家⾃然科学基⾦项⽬申请与结题等有关事项的通告 国科⾦发计〔2026〕2号 国家⾃然科学基⾦委员会（以下简称⾃然科学基⾦委）坚持以习近平新时代中国特⾊社会主义思想为指导，全⾯贯彻党的⼆⼗ 习近平总书记关于基础研究的重要论述和指⽰批⽰精神，深⼊贯彻落实党中央、国务院决策部署，在中央科技委员会的领导下，锚 准确把握我国基础研究发展历史⽅位和科学基⾦新的使命定位，持续优化科学基⾦管理体系，切实提升科学基⾦资助效能，为实现 技⾃⽴⾃强贡献更⼤⼒量。 按照国家⾃然科学基⾦（以下简称科学基⾦）资助管理⼯作安排，现将2026年度科学基⾦项⽬申请和2025年资助期满项⽬结题 【**1**】⼀、项⽬

- [ ] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 【**1**】处应该截断，后续读取了不完整的具体项目内容

## 10. Chunk 70

- Document: 关于2026年度国家自然科学基金项目申请与结题等有关事项的通告
- Type: call_snapshot / constraint
- Page: 5-5
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 10
- Automatic markers: clause
- Excerpt: 备案内容包括正式印发并加盖单位公章的包⼲制内部管理规定纸质⽂件和电⼦⽂件（扫描件）。 纸质⽂件邮寄⾄国家⾃然科学基 址：北京市海淀区双清路83号财务局经费管理处，邮编：100085，电话：010-62328383。 电⼦⽂件直接发送到邮箱JFGLC@nsfc. g 四、材料接收 （⼀）材料接收组负责统⼀接收依托单位送达或邮寄的材料，不接收个⼈直接报送和⾮依托单位报送的材料。 （⼆）材料接收组办公地点设在⾃然科学基⾦委⾏政楼101房间。 【**1**】五、其他注意事项 （⼀）申请书、项⽬进展报告、结题/成果报告中，不得出现国家《科学技术保密规定》中列举的属于国家科学技术秘密范围的 科技安全规定的涉密信息、敏感

- [ ] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 【**1**】处应该截断，后续读取了不完整的具体项目内容

## 11. Chunk 71

- Document: 2026年度国家自然科学基金项目申请手册
- Type: call_snapshot / constraint
- Page: 1-1
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 0
- Automatic markers: date_or_year
- Excerpt: 2026年度国家自然科学基金项目 申请手册 （内部资料，切勿外传） 香港中文大学（深圳）科研处 编制 2026 年 1 月

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 正确，但是信息无用

## 12. Chunk 114

- Document: 2026年度国家自然科学基金项目申请手册
- Type: call_snapshot / constraint
- Page: 38-38
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 43
- Automatic markers: clause
- Excerpt: 第十九条 本办法自印发之日起施行。【**1**】 37

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 【**1**】这里读取了页码，应该去掉

## 13. Chunk 115

- Document: 国家自然科学基金2026年申请注意事项
- Type: call_snapshot / constraint
- Page: 1-1
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 0
- Automatic markers: none
- Excerpt: 国家自然科学基金2026年申请注意事项 科学技术研究院 2026年

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 正确，但是信息无用

## 14. Chunk 143

- Document: 国家自然科学基金2026年申请注意事项
- Type: call_snapshot / constraint
- Page: 29-29
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 28
- Automatic markers: none
- Excerpt: 合作创新团队项目--申报协议书内容与模板保持一致，不可擅自更改 1. 所在学院/附属医院需加强审核，确保申请人所提交申请材料的真实性、完整性和合规性。 2. 需保证资助期限内每年在依托单位从事基础研究工作的时间在6个月以上。 ----项目获批开始执行后，需符合该要求。 3. 与依托单位须签署协议（若申请人在申请阶段有国外全职工作单位，须请国外单位知悉）：----由学院科研秘书统一申请 （1）协议需使用基金委指南通知中的“合作创新研究团队项目申报协议书”模板，姓名需与基金委系统中保持一致，正确填 写职称信息； （2）若申请人在申请阶段有国外全职工作单位，为避免后续出现纠纷，须出具国外单位知悉的相【**1**】

- [ ] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 【**1**】处信息不全，没有读取后续的完整信息内容

## 15. Chunk 144

- Document: 国家自然科学基金申请书撰写范例2024版
- Type: successful_case / style
- Page: 1-1
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 0
- Automatic markers: none
- Excerpt: 国家自然科学基金申请书 申请代码： 受理部门： 收件日期： 受理编号： 国家自然科学基金申请书 由系统自动生成 撰写范例 （2024版） 各类型申请书均采用在线方式申报， 全面开展无纸化申请 相关内容请以 2024 年申报指南为准 请在填报前认真阅读各类型项目申报指南 国家自然科学基金委员会

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 正确

## 16. Chunk 163

- Document: 国家自然科学基金申请书撰写范例2024版
- Type: successful_case / style
- Page: 14-14
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 19
- Automatic markers: none
- Excerpt: 国家自然科学基金申请书 附件（逐项上传，请参照各类项目填报说明，不同类别项目要求不一） 上传的电子附件材料应为项目申请人和主要参与者取得的代表性成果 或者科技奖励。 1．提供 5 篇以内申请人本人发表的与申请项目相关的代表性论文电子 版文件； 2．如上传专著，可以只提供著作封面、摘要、目录、版权页等； 3．如上传所获科技奖励，应提供国家级科技奖励（国家自然科学奖、 国家发明奖、国家科学技术进步奖）、省部级奖励（二等以上）奖励证书的 电子版扫描文件； 4．如上传专利或其他公认突出的创造性成果或成绩，应提供证明材料 的电子版扫描文件； 5．在国际学术会议上作大会报告、特邀报告，应提供邀请信或通知的【**1**】

- [ ] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 【**1**】处信息不全，没有读取后续的完整信息内容

## 17. Chunk 164

- Document: 国自然征文撰写指导
- Type: successful_case / style
- Page: 1-1
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 0
- Automatic markers: clause
- Excerpt: 报告正文撰写指导（仅供参考） （一）成功申请要素： ⚫ 创新思想：创新是第一要素，未来研究基石 ⚫ 研究实力：研究基础、成果质量、研究团队 ⚫ 写作技巧：准确、清晰、具体、简洁 ⚫ 在熟悉的领域做擅长的事情 （二）题目 ⚫ 是申请人对评审专家说的第一句话 ⚫ 三要素:明确研究对象（主体）、明确要解决的科学问题、明确采用的、解决 问题的方法：科学方法 ⚫ 题目是研究方向的总结，宜具体、集中，忌宽泛、发散、抽象，不宜过长（不 要超过 30 字） ⚫ 建议在大数据知识管理平台系统中（ [https://kd](https://kd). nsfc. cn/ ） 检索，忌讳题目 名称重复 （三） 立项依据与研究内容 各部分内容逻辑

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 

## 18. Chunk 170

- Document: 国自然征文撰写指导
- Type: successful_case / style
- Page: 5-5
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 6
- Automatic markers: none
- Excerpt: 【**1**】需求动态变化、供应风险及供 应链成员的风险态度等疫苗供应链的特点，探索顾客选择行为对供应链决策的影 响，寻求最佳供应链决策；研究信息不对称下基于顾客选择行为的疫苗类生物制 品供应链信息共享及协调机制。 本项目的研究将拓展供应链领域的理论和方法， 有助于了解顾客选择行为对疫苗类生物制品供应链决策和绩效的影响，为政府有 效管理疫苗类生物制品供应链以应对传染病威胁，提升人们的健康水平具有重要 的现实意义。 【**2**】处信息不全5

- [ ] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 1.【**1**】处信息不全，没有读取前面的完整信息内容
- 2.【**2**】处错误读取到页码

## 19. Chunk 171

- Document: 2026年度国家自然科学基金形式审查表
- Type: review_criteria / constraint
- Page: 1-1
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 0
- Automatic markers: none
- Excerpt: 2026 年度国家自然科学基金形式审查表 请申请人将明细表打印一份，在申请书提交前逐项认真审查，并在右边“□”处打√。 本表与《指南》不一致的， 以《指南》为准。 该表请在开学后由学院收齐留存，以备核查。 总体 项目指南 科研诚信 申请书 限项检查 1 2 3 4 5 6 申请人资格 7 8 身份 已学习《2026 年项目指南》和《申请须知》，认真研读了申请书所涉及的相关项目类型和 相关学部、学科的要求。 申报项目的研究内容符合申报学科和项目类型的资助范围。 提示：目前不属于申报学科资助范畴已成为形式审查不合格的最主要原因，请关注相关学 部各学科明确不受理的研究内容（详见指南），请重点关注生命【**1**】

- [ ] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 【**1**】处信息不全，没有读取后面的完整信息内容

## 20. Chunk 187

- Document: 2026年度国家自然科学基金形式审查表
- Type: review_criteria / constraint
- Page: 7-7
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 16
- Automatic markers: none
- Excerpt: 申请人承诺： 本人提交的国家自然科学基金项目申请书为本人所写，内容真实，未涉及任何违反法律及涉 密内容；本人及课题组成员不存在超项情况，人员信息真实、准确，课题成员知情并同意参加本 项目，本人及课题成员均为亲笔签名；项目中合作单位（有合作单位的）科研管理部门知情并同 意其单位人员参加本项目研究，加盖的法人公章真实、有效。 本人已依据形式审查表（上表）对申请书内容进行了认真核对，申请书所有内容均符合形式 审查要求。 本人和项目组成员对申请书所涉及内容的真实性、完整性和合规性负责。 申请人签字： 2026 年 3 月 日 二级单位承诺： 学院已依据形式审查表（上表）对项目负责人的申请书内容进行了认【**1**】

- [ ] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 【**1**】处信息不全，没有读取后面的完整信息内容

## 21. Chunk 188

- Document: 北京大学2026年度国家自然科学基金项目形式审查明细表
- Type: review_criteria / constraint
- Page: 1-1
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 0
- Automatic markers: none
- Excerpt: 北京大学 2026 年度国家自然科学基金项目形式审查明细表 1. 使用说明： （1）建议申请人打印本表，仔细对照申请书，逐项认真自查，并在右侧“确认”列打勾 （2）建议院系科研秘书老师参考本明细表进行审核 2. 时间节点: （1）基金系统提交截止时间：3 月 4 日中午 12:00 （2）院系系统提交截止时间：按照各院系通知要求。 总体情况 【申请人资格核查】 （1）具有高级职称或博士学位； 1. 2. 3. （2）或者 2 名同领域高级职称专家推荐（系统内下载推荐信模板）； （3）在职研究生：提供导师同意函（系统内下载模板）； （4）非全职聘用人员：提供聘任合同复印件（人事部公章。 注意：聘【**1**】

- [ ] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 【**1**】处信息不全，没有读取后面的完整信息内容

## 22. Chunk 209

- Document: 北京大学2026年度国家自然科学基金项目形式审查明细表
- Type: review_criteria / constraint
- Page: 8-8
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 21
- Automatic markers: none
- Excerpt: 【**1**】简历中的职称、工作经历不一致（注意更新同步） ◆ 推荐信没有注明推荐人单位、专业和职称，没有签字、没有准确日期等 ◆ 未按所报类型项目的要求提供附件材料（仔细参阅《指南》&《填报说明与撰写提纲》） 8

- [ ] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 【**1**】处信息不全，没有读取前面的完整信息内容

## 23. Chunk 210

- Document: 国家自然科学基金项目评审回避与保密管理办法
- Type: review_criteria / constraint
- Page: 1-1
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 0
- Automatic markers: clause
- Excerpt: 三、项目评审与研究成果管理办法 国家自然科学基金项目评审回避与保密管理办法 （2015 年 5 月 12 日国家自然科学基金委员会第 5 次委务会议审议通过） 第一章 总 则 第一条 为了规范和加强国家自然科学基金（以下简称科学基金）项目评审 回避与保密管理工作，维护科学基金项目评审的公开、公平和公正，根据《国 家自然科学基金条例》，制定本办法。 第二条 各类科学基金项目评审过程中国家自然科学基金委员会（以下简称 自然科学基金委）工作人员、评审专家的回避与保密管理适用本办法。 自然科学基金委工作人员是指在职权范围内直接参与评审工作的委内人员， 包括在编人员、兼职人员、流动编制人员和兼聘人员。 

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 正确

## 24. Chunk 230

- Document: 国家自然科学基金项目评审回避与保密管理办法
- Type: review_criteria / constraint
- Page: 16-16
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 20
- Automatic markers: clause
- Excerpt: 第十六条 依托单位对于取得的项目成果知识产权应当依法实施，同时采取 保护措施。 对于按照有关法律规定的国家无偿实施或者许可他人有偿实施、无偿实施 的， 依托单位以及项目负责人和参与者应当积极配合。 第十七条 将项目成果形成的知识产权向境外的组织或者个人转让或者许可 境外的组织或者个人独占实施的，依托单位或者项目负责人应当按照有关国家 法律法规规定及时申请报批。 第十八条 自然科学基金委应当对项目成果进行分类统计。 对于突出的和重 要的资助项目成果，自然科学基金委可以通过有关刊物、报纸或者网站等媒介 进行宣传和报道。 取得重大成果的，项目负责人应当及时向自然科学基金委报送。【**1**】 第十九条 自然科学基

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 【**1**】处应该截断，后续读取了不完整的具体项目内容

## 25. Chunk 231

- Document: 项目申请书模板
- Type: template / template
- Page: 1-1
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 0
- Automatic markers: none
- Excerpt: 申请代码(Application Codes) 接收部门（Receiving Department） 收件日期（ReceivingDate） 接收编号（Admission No. ） 国家自然科学基金 优秀青年科学基金项目（海外） 申请书 Proposal for National Natural Science Fund for Excellent Young Scientists Fund Program(Overseas) （2 0 2 6版） 申请人（PrincipalInvestigator）： 专业领域（Area of Specialization）： 项目名称（Title of 

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 【**1**】处信息不全，没有读取后面的完整信息内容

## 26. Chunk 248

- Document: 项目申请书模板
- Type: template / template
- Page: 12-12
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 17
- Automatic markers: none
- Excerpt: 国家自然科学基金申请书 NSFC Grant Proposal 2026版 国家自然科学基金优秀青年科学基金项目（海外） 依托单位推荐意见 推荐内容 情况说明及意见 推荐理由及引进的 必要性 本单位该学科领域 的现有基础 支持条件 对申报人的涉法涉 诉、知识产权纠 纷、竞业禁止、兼 职取酬限制、被有 关部门调查等情况 的核实意见 申请人有关信息属实，本单位承诺予以上述支持，特推荐申报。 单位法人签字: 单位（公章） 年 月 日 （注：申请时，需要将本页签字盖章后的扫描件作为附件上传。 Please note that this page should be signed, scanned an【**1**】

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 【**1**】处信息不全，没有读取后面的完整信息内容

## 27. Chunk 249

- Document: 团队科研简历 合成测试资料
- Type: team_profile / fact
- Page: 1-1
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 0
- Automatic markers: none
- Excerpt: 团队科研简历 合成测试资料 重要说明：本文件为 RAG 与证据追溯流程的合成测试夹具。 内容为虚构示例，不代表真实人员、机构、经历或成果，禁止用于项目申请和事实陈述。 单位：成都某某大学 智能信息工程学院 一、成员甲 教授 研究方向：自动调制识别、无线信号智能处理、通信对抗。 职责示例：负责总体研究设计、关键算法路线与技术把关。 经验示例：开展过复杂电磁环境下调制方式识别与鲁棒特征学习研究。 二、成员乙 副教授 研究方向：深度学习通信信号分析、时频表征、低信噪比识别。 职责示例：负责数据集构建、模型训练和对比实验设计。 经验示例：参与过小样本自动调制识别和跨场景泛化方法研究。 三、成员丙 讲师

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 正确

## 28. Chunk 93

- Document: 2026年度国家自然科学基金项目申请手册
- Type: call_snapshot / constraint
- Page: 23-23
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 22
- Automatic markers: clause, amount_or_ratio
- Excerpt: 【**1**】金资助，则该社科基金项目必须结题且已获得《结项证书》，《结项证 书》需上传申请书附件； （8）主要参与者中的境外人员需上传签字后的知情同意书扫描件； （9）重点国际（地区）合作研究基金及外国学者研究基金项目所需 上传的附件请仔细阅读《指南》。 16. 申请人对申请材料的责任 申请人应当对申请材料的真实性和完整性负责，不得提交有涉密 内容的项目申请，严禁伪造研究内容或隐瞒个人相关信息。 17. 限项申请规定 （一）一般性规定 1. 申请人同年只能申请1项同类型项目◇1 ［重大研究计划项目中的集成项目 和战略研究项目、专项项目中的科技活动项目、国际（地区）合作交流项目除外］。 ◇1 同类型项目：对【**2**】

- [ ] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 【**1**】处信息不全，没有读取前面的完整信息内容
- 【**2**】处信息不全，没有读取后面的完整信息内容

## 29. Chunk 16

- Document: 2026年度国家自然科学基金项目申请规定
- Type: guideline / constraint
- Page: 8-8
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 15
- Automatic markers: clause
- Excerpt: 进入现场考察环节的卓越研究群 体项目申请、未进入预算评审环节的国家重大科研仪器研制项目（自由申请）申请、未 进入现场考察环节的国家重大科研仪器研制项目（部门推荐）申请，不计入申请和承担 项目总数范围。 2. 申请人即使受聘于多个依托单位，通过不同依托单位申请和承担项目，其申请 和承担的项目数量仍然适用于本限项申请规定。 3. 现行项目管理办法中，有关申请项目数量的要求与本限项申请规定不一致的， 以本规定为准。 三、预算编报要求 （一）总体要求 申请人要严格按照《国家自然科学基金资助项目资金管理办法》《国家自然科学基金 项目申请书预算编制说明》等要求，遵循“政策相符性、目标相关性、经济合理性”的【**1**】

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 【**1**】处信息不全，没有读取后面的完整信息内容

## 30. Chunk 129

- Document: 国家自然科学基金2026年申请注意事项
- Type: call_snapshot / constraint
- Page: 15-15
- Heading: HEADING_EXTRACTION_NEEDED
- Chunk index: 14
- Automatic markers: clause, amount_or_ratio
- Excerpt: 申请规定：限项规定 2. 不计入申请和承担项目总数范围的项目类型 数学天元基金项目、直接费用小于或等于 200 万元/项的组织间国际（地区）合作研究项目、国际（地区）合作交流项目、重大研 究计划项目中的集成项目和战略研究项目、外国学者研究基金项目、合作创新研究团队项目、专项项目中的科技活动项目、资助期限 1 年及以下的其他类型项目，以及项目指南中特别说明不受申请和承担项目总数限制的项目等。 （三）部分项目类型的特殊规定： 1. 重点项目：作为申请人申请和作为项目负责人正在承担的重点项目数量合计限 1 项，申请当年资助期满的项目不计入统计范围。 2. 国际（地区）合作类项目 作为申请人申请和作为【**1**】

- [x] Semantic completeness
- [x] Page correctness
- [x] Heading correctness or extraction needed
- [x] Clause number preservation
- [x] Amount and date preservation
- [x] Classification correctness

- Notes:
- 【**1**】处信息不全，没有读取后面的完整信息内容

