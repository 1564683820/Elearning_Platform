// E-Learning 比赛项目讲解PPT 生成脚本
const pptxgen = require("pptxgenjs"), React = require("react"), ReactDOMServer = require("react-dom/server"), sharp = require("sharp");
const rIc=(I,c="#5B9E6F",s=256)=>ReactDOMServer.renderToStaticMarkup(React.createElement(I,{color:c,size:String(s)}));
const i2d=async(I,c,s=256)=>"image/png;base64,"+(await sharp(Buffer.from(rIc(I,c,s))).png().toBuffer()).toString("base64");
const C={primary:"5B9E6F",strong:"2d7d46",mid:"3d7a4e",soft:"88c8a0",bg:"e6f7e6",bg2:"d4edda",dark:"1a4d2e",white:"FFFFFF",text:"2d3748",textSec:"4a5568",textLight:"718096",cardBg:"F7FAF7"};
const FT="Georgia",FB="Calibri",mkSh=()=>({type:"outer",color:"000000",blur:8,offset:2,angle:135,opacity:0.10}),mkCs=()=>({type:"outer",color:"000000",blur:6,offset:1,angle:135,opacity:0.08});

async function main(){
 const{Ga:Ga,FaRobot,FaBookOpen,FaMicrophoneAlt,FaFilePowerpoint,FaClipboardList,FaLightbulb,FaGraduationCap,FaChartBar,FaUsers,FaComments,FaQuestionCircle,FaCheckCircle,FaArrowRight,FaStar,FaBrain,FaProjectDiagram,FaLanguage,FaNetworkWired,FaRocket}=require("react-icons/fa");
 const im={r:FaRobot,b:FaBookOpen,m:FaMicrophoneAlt,p:FaFilePowerpoint,cl:FaClipboardList,l:FaLightbulb,g:FaGraduationCap,ch:FaChartBar,u:FaUsers,cm:FaComments,q:FaQuestionCircle,ck:FaCheckCircle,ar:FaArrowRight,st:FaStar,br:FaBrain,pj:FaProjectDiagram,la:FaLanguage,nw:FaNetworkWired,rk:FaRocket};
 const D={};for(const[k,I]of Object.entries(im))D[k]=await i2d(I);
 D.ck2=await i2d(FaCheckCircle,"#2d7d46");D.m2=await i2d(FaMicrophoneAlt,"#2d7d46");D.p2=await i2d(FaFilePowerpoint,"#2d7d46");D.cl2=await i2d(FaClipboardList,"#2d7d46");D.br2=await i2d(FaBrain,"#2d7d46");D.cm2=await i2d(FaComments,"#2d7d46");
 const pres=new pptxgen();pres.layout="LAYOUT_16x9";pres.author="E-Learning Team";pres.title="E-Learning 智能英语学习平台";

 // S1 Cover
 {let s=pres.addSlide();s.background={color:C.dark};
 s.addShape(pres.shapes.RECTANGLE,{x:0,y:0,w:10,h:0.06,fill:{color:C.soft}});
 s.addShape(pres.shapes.RECTANGLE,{x:.7,y:1.1,w:.07,h:2.4,fill:{color:C.soft}});
 s.addShape(pres.shapes.OVAL,{x:7.5,y:-.8,w:3.5,h:3.5,fill:{color:C.strong,transparency:40}});
 s.addShape(pres.shapes.OVAL,{x:8.2,y:-.3,w:2.5,h:2.5,fill:{color:C.mid,transparency:50}});
 s.addText("E-Learning",{x:1.1,y:1.2,w:7,h:.9,fontSize:48,fontFace:FT,color:C.white,bold:true,margin:0});
 s.addText("智能英语学习平台",{x:1.1,y:2,w:7,h:.6,fontSize:24,fontFace:FB,color:C.soft,margin:0});
 s.addText("AI驱动 \u00B7 情景教学 \u00B7 全阶段覆盖",{x:1.1,y:2.7,w:7,h:.4,fontSize:13,fontFace:FB,color:C.bg2,margin:0});
 s.addShape(pres.shapes.LINE,{x:1.1,y:3.4,w:3.5,h:0,line:{color:C.mid,width:1.5}});
 s.addText("比赛项目汇报",{x:1.1,y:3.7,w:5,h:.4,fontSize:13,fontFace:FB,color:C.textLight,margin:0});
 s.addShape(pres.shapes.RECTANGLE,{x:0,y:5.2,w:10,h:.425,fill:{color:C.strong,transparency:40}});}

 // S2 产品简介
 {let s=pres.addSlide();s.background={color:C.white};
 s.addShape(pres.shapes.RECTANGLE,{x:0,y:0,w:10,h:.06,fill:{color:C.primary}});
 s.addShape(pres.shapes.RECTANGLE,{x:0,y:.06,w:.15,h:5.565,fill:{color:C.bg}});
 s.addText("产品简介",{x:.6,y:.3,w:5,h:.6,fontSize:30,fontFace:FT,color:C.strong,bold:true,margin:0});
 s.addShape(pres.shapes.LINE,{x:.6,y:.95,w:2,h:0,line:{color:C.soft,width:2}});
 s.addText("产品定位",{x:.6,y:1.3,w:4,h:.4,fontSize:16,fontFace:FB,color:C.text,bold:true,margin:0});
 s.addShape(pres.shapes.RECTANGLE,{x:.6,y:1.75,w:4.2,h:2.6,fill:{color:C.cardBg},shadow:mkCs()});
 s.addText([{text:"给启蒙至雅思阶段的全年龄英语学习者使用的",options:{breakLine:true,fontSize:13,color:C.textSec}},{text:"微信小程序 + 教师Web管理端",options:{breakLine:true,fontSize:13,color:C.strong,bold:true}},{text:"",options:{breakLine:true,fontSize:8}},{text:"核心价值：",options:{breakLine:true,fontSize:13,color:C.text,bold:true}},{text:"\u2706 AI驱动的情景记忆与智能对话",options:{breakLine:true,fontSize:12,color:C.textSec}},{text:"\u2706 覆盖全学习阶段的体系化训练",options:{breakLine:true,fontSize:12,color:C.textSec}},{text:"\u2706 错题闭环复习机制",options:{fontSize:12,color:C.textSec}}],{x:.85,y:1.95,w:3.7,h:2.2,fontFace:FB,valign:"top",margin:0,paraSpaceAfter:4});
 s.addText("功能概览",{x:5.4,y:1.3,w:4,h:.4,fontSize:16,fontFace:FB,color:C.text,bold:true,margin:0});
 [["智能对话",D.cm],["情景训练",D.la],["AI备课PPT",D.p],["错题本",D.cl],["语音对话",D.m],["考试管理",D.q],["知识图谱",D.pj],["教学助手",D.br]].forEach(([lb,ic],i)=>{let col=i%2,row=Math.floor(i/2),cx=5.4+col*2.2,cy=1.85+row*1.25;s.addShape(pres.shapes.RECTANGLE,{x:cx,y:cy,w:1.9,h:1,fill:{color:C.bg},shadow:mkCs()});s.addShape(pres.shapes.OVAL,{x:cx+.15,y:cy+.2,w:.55,h:.55,fill:{color:C.primary}});s.addImage({data:ic,x:cx+.24,y:cy+.29,w:.37,h:.37});s.addText(lb,{x:cx+.8,y:cy+.25,w:.95,h:.55,fontSize:12,fontFace:FB,color:C.text,bold:true,valign:"middle",margin:0});});
 s.addShape(pres.shapes.RECTANGLE,{x:.6,y:4.6,w:8.8,h:.75,fill:{color:C.bg2}});
 s.addText([{text:"目标用户：",options:{bold:true,fontSize:11,color:C.strong}},{text:"K12学生（4-15岁）",options:{fontSize:11,color:C.textSec}},{text:"  |  ",options:{fontSize:11,color:C.border}},{text:"考试导向学习者（18-30岁）",options:{fontSize:11,color:C.textSec}},{text:"  |  ",options:{fontSize:11,color:C.border}},{text:"自我提升者",options:{fontSize:11,color:C.textSec}}],{x:.8,y:4.65,w:8.4,h:.6,fontFace:FB,valign:"middle",margin:0});}

 // S3 产品功能
 {let s=pres.addSlide();s.background={color:C.white};
 s.addShape(pres.shapes.RECTANGLE,{x:0,y:0,w:10,h:.06,fill:{color:C.primary}});
 s.addText("产品功能",{x:.6,y:.3,w:5,h:.6,fontSize:30,fontFace:FT,color:C.strong,bold:true,margin:0});
 s.addShape(pres.shapes.LINE,{x:.6,y:.95,w:2,h:0,line:{color:C.soft,width:2}});
 let cards=[{t:"情景对话（语音）",st:"新增核心功能",ic:D.m,hi:true,its:["10大真实场景（咖啡店/餐厅/购物等）","3级难度（初/中/高级自适应）","TTS语音合成+语音识别(STT)","WebSocket实时语音对话","AI语法/词汇/流利度评分"]},{t:"AI备课系统",st:"教师端核心功能",ic:D.p,hi:false,its:["4种课型（新授课/复习课等）","知识图谱自动生成课程结构","AI生成完整PPT幻灯片","在线编辑与课堂互动","投票/弹幕/随堂测验"]},{t:"训练与测评",st:"全体系训练",ic:D.cl,hi:false,its:["单词记忆+短语语法+句子翻译","阅读训练+听力训练","AI智能组卷与自动评分","错题本自动收录与归类","AI错题总结报告生成"]}];
 cards.forEach((c,i)=>{let cx=.6+i*3.2;s.addShape(pres.shapes.RECTANGLE,{x:cx,y:1.3,w:2.8,h:4,fill:{color:c.hi?C.bg:C.cardBg},shadow:c.hi?mkSh():mkCs(),line:c.hi?{color:C.primary,width:1.5}:undefined});
 if(c.hi){s.addShape(pres.shapes.RECTANGLE,{x:cx,y:1.3,w:2.8,h:.05,fill:{color:C.primary}});s.addShape(pres.shapes.RECTANGLE,{x:cx+2.05,y:1.2,w:.75,h:.3,fill:{color:C.strong}});s.addText("NEW",{x:cx+2.05,y:1.2,w:.75,h:.3,fontSize:10,fontFace:FB,color:C.white,bold:true,align:"center",valign:"middle",margin:0});}
 s.addShape(pres.shapes.OVAL,{x:cx+1.05,y:1.55,w:.7,h:.7,fill:{color:c.hi?C.strong:C.primary}});s.addImage({data:c.ic,x:cx+1.16,y:1.66,w:.48,h:.48});
 s.addText(c.t,{x:cx+.2,y:2.35,w:2.4,h:.35,fontSize:14,fontFace:FB,color:C.text,bold:true,align:"center",margin:0});s.addText(c.st,{x:cx+.2,y:2.65,w:2.4,h:.25,fontSize:10,fontFace:FB,color:C.textLight,align:"center",margin:0});
 let ck=c.hi?D.ck2:D.ck;c.its.forEach((it,j)=>{let iy=3.1+j*.45;s.addImage({data:ck,x:cx+.25,y:iy+.06,w:.22,h:.22});s.addText(it,{x:cx+.55,y:iy,w:2.05,h:.35,fontSize:10,fontFace:FB,color:C.textSec,valign:"top",margin:0});});});}

 // S4 用户反馈（占位）
 {let s=pres.addSlide();s.background={color:C.dark};
 s.addShape(pres.shapes.RECTANGLE,{x:0,y:0,w:10,h:.06,fill:{color:C.soft}});
 s.addImage({data:D.cm,x:4.5,y:1.2,w:1,h:1});s.addText("用户反馈",{x:1,y:2.3,w:8,h:.7,fontSize:36,fontFace:FT,color:C.white,bold:true,align:"center",margin:0});
 s.addShape(pres.shapes.LINE,{x:4,y:3.2,w:2,h:0,line:{color:C.soft,width:2}});s.addText("（内容待补充）",{x:1,y:3.4,w:8,h:.5,fontSize:16,fontFace:FB,color:C.textLight,align:"center",margin:0});
 s.addShape(pres.shapes.OVAL,{x:-1,y:3.5,w:3,h:3,fill:{color:C.strong,transparency:50}});s.addShape(pres.shapes.OVAL,{x:8,y:-1,w:3,h:3,fill:{color:C.mid,transparency:60}});
 s.addShape(pres.shapes.RECTANGLE,{x:0,y:5.2,w:10,h:.425,fill:{color:C.strong,transparency:40}});}

 // S5 班级知识库
 {let s=pres.addSlide();s.background={color:C.white};
 s.addShape(pres.shapes.RECTANGLE,{x:0,y:0,w:10,h:.06,fill:{color:C.primary}});s.addText("关键技术实现",{x:.6,y:.3,w:5,h:.55,fontSize:26,fontFace:FT,color:C.strong,bold:true,margin:0});
 s.addShape(pres.shapes.LINE,{x:.6,y:.85,w:1.8,h:0,line:{color:C.soft,width:2}});s.addShape(pres.shapes.RECTANGLE,{x:.6,y:1.15,w:8.8,h:.55,fill:{color:C.bg}});
 s.addImage({data:D.nw,x:.78,y:1.23,w:.38,h:.38});s.addText("班级知识库系统",{x:1.3,y:1.15,w:7.5,h:.55,fontSize:18,fontFace:FB,color:C.strong,bold:true,valign:"middle",margin:0});
 s.addText("架构设计",{x:.6,y:1.95,w:4,h:.35,fontSize:14,fontFace:FB,color:C.text,bold:true,margin:0});
 [["文档上传与解析","支持PDF/Word/PPT/图片，自动提取文本"],["向量化存储","BGE-large-zh嵌入\u2192 1024维Milvus向量库"],["混合检索","稠密向量+BM25稀疏检索双重召回"],["Auto-merging","自动合并细粒度块为大块上下文"],["RAG问答","检索增强生成，基于班级文档精准回答"]].forEach(([lb,ds],i)=>{let iy=2.45+i*.5;s.addShape(pres.shapes.RECTANGLE,{x:.7,y:iy,w:.12,h:.12,fill:{color:C.primary}});s.addText([{text:lb,options:{bold:true,fontSize:11,color:C.text}},{text:" — "+ds,options:{fontSize:10,color:C.textSec}}],{x:.95,y:iy-.03,w:3.8,h:.4,fontFace:FB,valign:"top",margin:0});});
 s.addText("技术亮点",{x:5.4,y:1.95,w:4,h:.35,fontSize:14,fontFace:FB,color:C.text,bold:true,margin:0});
 [["7","Milvus集合","学生错题/教师文档/对话历史"],["2.83MB","BM25语料库","稀疏检索增强召回"],["多维度","RAG策略","查询重写+时效权重+权限隔离"]].forEach(([num,lb,ds],i)=>{let hy=2.45+i*.75;s.addShape(pres.shapes.RECTANGLE,{x:5.4,y:hy,w:4,h:.6,fill:{color:C.bg2},shadow:mkCs()});s.addText(num,{x:5.55,y:hy+.05,w:1,h:.5,fontSize:22,fontFace:FT,color:C.strong,bold:true,valign:"middle",margin:0});s.addText([{text:lb,options:{bold:true,fontSize:12,color:C.text,breakLine:true}},{text:ds,options:{fontSize:10,color:C.textSec}}],{x:6.6,y:hy+.03,w:2.6,h:.54,fontFace:FB,valign:"middle",margin:0});});}

 // S6 情景对话语音
 {let s=pres.addSlide();s.background={color:C.white};
 s.addShape(pres.shapes.RECTANGLE,{x:0,y:0,w:10,h:.06,fill:{color:C.primary}});s.addText("关键技术实现",{x:.6,y:.3,w:5,h:.55,fontSize:26,fontFace:FT,color:C.strong,bold:true,margin:0});
 s.addShape(pres.shapes.LINE,{x:.6,y:.85,w:1.8,h:0,line:{color:C.soft,width:2}});s.addShape(pres.shapes.RECTANGLE,{x:.6,y:1.15,w:8.8,h:.55,fill:{color:C.bg}});
 s.addImage({data:D.m2,x:.78,y:1.23,w:.38,h:.38});s.addText("情景对话语音系统",{x:1.3,y:1.15,w:7.5,h:.55,fontSize:18,fontFace:FB,color:C.strong,bold:true,valign:"middle",margin:0});
 [["语音输入","麦克风录音PCM音频"],["语音识别","SiliconFlow Whisper"],["AI对话","情景语境理解纠错"],["语音合成","火山引擎TTS v3"],["语音输出","多音色实时播放"]].forEach(([t,ds],i)=>{let sx=.65+i*1.75,sy=1.95;s.addShape(pres.shapes.RECTANGLE,{x:sx,y:sy,w:1.55,h:1.75,fill:{color:C.bg},shadow:mkCs()});s.addShape(pres.shapes.OVAL,{x:sx+.475,y:sy+.15,w:.6,h:.6,fill:{color:C.primary}});s.addText(String(i+1),{x:sx+.475,y:sy+.15,w:.6,h:.6,fontSize:18,fontFace:FT,color:C.white,bold:true,align:"center",valign:"middle",margin:0});s.addText(t,{x:sx+.1,y:sy+.85,w:1.35,h:.3,fontSize:12,fontFace:FB,color:C.text,bold:true,align:"center",margin:0});s.addText(ds,{x:sx+.1,y:sy+1.15,w:1.35,h:.55,fontSize:9,fontFace:FB,color:C.textSec,align:"center",valign:"top",margin:0});if(i<4)s.addImage({data:D.ar,x:sx+1.58,y:sy+.775,w:.14,h:.14});});
 [["10大场景","咖啡店/餐厅/购物/问路等",C.strong],["3级难度","Beginner/Intermediate/Advanced",C.mid],["实时交互","WebSocket+Realtime API",C.primary],["AI评分","语法/词汇/流利度/发音",C.soft]].forEach(([t,ds,cl],i)=>{let ix=.6+i*2.35;s.addShape(pres.shapes.RECTANGLE,{x:ix,y:4.05,w:2.15,h:1.2,fill:{color:C.cardBg},shadow:mkCs()});s.addShape(pres.shapes.RECTANGLE,{x:ix,y:4.05,w:.07,h:1.2,fill:{color:cl}});s.addText(t,{x:ix+.2,y:4.1,w:1.8,h:.35,fontSize:13,fontFace:FB,color:C.text,bold:true,margin:0});s.addText(ds,{x:ix+.2,y:4.45,w:1.8,h:.7,fontSize:9.5,fontFace:FB,color:C.textSec,valign:"top",margin:0});});}

 // S7 PPT/试卷生成
 {let s=pres.addSlide();s.background={color:C.white};
 s.addShape(pres.shapes.RECTANGLE,{x:0,y:0,w:10,h:.06,fill:{color:C.primary}});s.addText("关键技术实现",{x:.6,y:.3,w:5,h:.55,fontSize:26,fontFace:FT,color:C.strong,bold:true,margin:0});
 s.addShape(pres.shapes.LINE,{x:.6,y:.85,w:1.8,h:0,line:{color:C.soft,width:2}});
 [[D.p2,"AI备课PPT生成",["4种课型","知识图谱自动提取结构","两阶段：确认后生成","在线编辑+课堂互动"]],[D.cl2,"AI组卷 & 批改",["按知识点/难度出题","题型覆盖5种","AI评分+手动调整","自动同步错题本"]]].forEach(([ic,tl,its],idx)=>{let lx=idx?5.2:.6;s.addShape(pres.shapes.RECTANGLE,{x:lx,y:1.15,w:4.2,h:.5,fill:{color:C.bg}});s.addImage({data:ic,x:lx+.15,y:1.21,w:.35,h:.35});s.addText(tl,{x:lx+.6,y:1.15,w:3.4,h:.5,fontSize:15,fontFace:FB,color:C.strong,bold:true,valign:"middle",margin:0});s.addShape(pres.shapes.RECTANGLE,{x:lx,y:1.8,w:4.2,h:2.4,fill:{color:C.cardBg},shadow:mkCs()});
 its.forEach((it,i)=>{let iy=2+i*.52;s.addShape(pres.shapes.OVAL,{x:lx+.2,y:iy+.06,w:.14,h:.14,fill:{color:C.primary}});s.addText(it,{x:lx+.45,y:iy,w:3.55,h:.4,fontSize:11,fontFace:FB,color:C.textSec,valign:"top",margin:0});});});
 s.addShape(pres.shapes.RECTANGLE,{x:.6,y:4.2,w:8.8,h:.06,fill:{color:C.soft}});
 s.addText("工作流程",{x:.6,y:4.35,w:2,h:.35,fontSize:13,fontFace:FB,color:C.text,bold:true,margin:0});
 ["教师输入","AI生成图谱","教师确认","生成幻灯片","课堂互动"].forEach((lb,i)=>{let wx=.6+i*1.85;s.addShape(pres.shapes.RECTANGLE,{x:wx,y:4.75,w:1.55,h:.5,fill:{color:C.bg},shadow:mkCs()});s.addText(lb,{x:wx,y:4.75,w:1.55,h:.5,fontSize:10,fontFace:FB,color:C.strong,bold:true,align:"center",valign:"middle",margin:0});if(i<4)s.addImage({data:D.ar,x:wx+1.58,y:4.85,w:.22,h:.22});});}

 // S8 错题报告总结
 {let s=pres.addSlide();s.background={color:C.white};
 s.addShape(pres.shapes.RECTANGLE,{x:0,y:0,w:10,h:.06,fill:{color:C.primary}});s.addText("关键技术实现",{x:.6,y:.3,w:5,h:.55,fontSize:26,fontFace:FT,color:C.strong,bold:true,margin:0});
 s.addShape(pres.shapes.LINE,{x:.6,y:.85,w:1.8,h:0,line:{color:C.soft,width:2}});s.addShape(pres.shapes.RECTANGLE,{x:.6,y:1.15,w:8.8,h:.55,fill:{color:C.bg}});
 s.addImage({data:D.br2,x:.78,y:1.23,w:.38,h:.38});s.addText("AI错题报告总结系统",{x:1.3,y:1.15,w:7.5,h:.55,fontSize:18,fontFace:FB,color:C.strong,bold:true,valign:"middle",margin:0});
 [["数据采集层","\u25CF单词训练错题收录","\u25CF试卷AI评分错题提取","\u25CF学习数据追踪","\u25CF多维度错误归类",C.strong],["智能分析层","\u25CF AI意图识别8种","\u25CF Milvus语义搜索","\u25CF错误模式分析","\u25CF Markdown报告生成",C.mid],["交互应用层","\u25CF助手自然语言查询","\u25CF错题导出PDF","\u25CF统计分析看板","\u25CF针对性练习推荐",C.primary]].forEach(([tl,...rest],i)=>{let lx=.6+i*3.1;s.addShape(pres.shapes.RECTANGLE,{x:lx,y:1.95,w:2.85,h:2.8,fill:{color:C.cardBg},shadow:mkCs()});let clr=rest[rest.length-1];s.addShape(pres.shapes.RECTANGLE,{x:lx,y:1.95,w:2.85,h:.5,fill:{color:clr}});s.addText(tl,{x:lx,y:1.95,w:2.85,h:.5,fontSize:13,fontFace:FB,color:C.white,bold:true,align:"center",valign:"middle",margin:0});let items=rest.slice(0,-1);items.forEach((it,j)=>{s.addText(it,{x:lx+.15,y:2.6+j*.5,w:2.55,h:.4,fontSize:10,fontFace:FB,color:C.textSec,valign:"top",margin:0});});});
 s.addShape(pres.shapes.RECTANGLE,{x:.6,y:5,w:8.8,h:.45,fill:{color:C.bg}});
 s.addText([{text:"教学场景：",options:{bold:true,fontSize:11,color:C.strong}},{text:"\"帮我总结钟离这周的错题\"\u2192跨班级搜索\u2192AI报告\u2192推荐",options:{fontSize:11,color:C.textSec}}],{x:.8,y:5,w:8.4,h:.45,fontFace:FB,valign:"middle",margin:0});}

 // S9 未来规划
 {let s=pres.addSlide();s.background={color:C.white};
 s.addShape(pres.shapes.RECTANGLE,{x:0,y:0,w:10,h:.06,fill:{color:C.primary}});s.addText("未来规划",{x:.6,y:.3,w:5,h:.6,fontSize:30,fontFace:FT,color:C.strong,bold:true,margin:0});
 s.addShape(pres.shapes.LINE,{x:.6,y:.95,w:2,h:0,line:{color:C.soft,width:2}});
 [["短期优化",C.strong,["AI生成内容质量提升","错题报告更精准关联","语音识别准确率优化","系统性能与响应速度"]],["中期功能",C.mid,["独立App(iOS/Android)","自适应学习路径推荐","多语言支持扩展","同伴学习与对战模式"]],["长期愿景",C.primary,["AI虚拟外教对话","智能学习规划师","教育资源共享平台","全球语言学习社区"]]].forEach(([t,cl,its],i)=>{let lx=.6+i*3.1;s.addShape(pres.shapes.RECTANGLE,{x:lx,y:1.3,w:2.85,h:3.5,fill:{color:C.cardBg},shadow:mkCs()});s.addShape(pres.shapes.RECTANGLE,{x:lx,y:1.3,w:2.85,h:.55,fill:{color:cl}});s.addText(t,{x:lx,y:1.3,w:2.85,h:.55,fontSize:14,fontFace:FB,color:C.white,bold:true,align:"center",valign:"middle",margin:0});its.forEach((it,j)=>{let iy=2.1+j*.55;s.addShape(pres.shapes.OVAL,{x:lx+.25,y:iy+.06,w:.12,h:.12,fill:{color:cl}});s.addText(it,{x:lx+.5,y:iy,w:2.2,h:.4,fontSize:12,fontFace:FB,color:C.text,valign:"top",margin:0});});});
 // Timeline arrow
 s.addImage({data:D.rk,x:4.2,y:5.15,w:.35,h:.35});s.addText("持续迭代，不断进化",{x:4.65,y:5.1,w:4.5,h:.4,fontSize:12,fontFace:FB,color:C.textLight,valign:"middle",margin:0});}

 // S10 致谢
 {let s=pres.addSlide();s.background={color:C.dark};
 s.addShape(pres.shapes.RECTANGLE,{x:0,y:0,w:10,h:.06,fill:{color:C.soft}});
 s.addShape(pres.shapes.OVAL,{x:8,y:4,w:3,h:3,fill:{color:C.strong,transparency:40}});
 s.addShape(pres.shapes.OVAL,{x:-1,y:-1,w:3,h:3,fill:{color:C.mid,transparency:50}});
 s.addText("感谢聆听",{x:1,y:1.5,w:8,h:1,fontSize:44,fontFace:FT,color:C.white,bold:true,align:"center",margin:0});
 s.addShape(pres.shapes.LINE,{x:3.5,y:2.7,w:3,h:0,line:{color:C.soft,width:2}});
 s.addText("期待您的宝贵意见",{x:1,y:2.9,w:8,h:.5,fontSize:18,fontFace:FB,color:C.soft,align:"center",margin:0});
 s.addText("E-Learning 智能英语学习平台",{x:1,y:3.6,w:8,h:.4,fontSize:14,fontFace:FB,color:C.textLight,align:"center",margin:0});
 s.addShape(pres.shapes.RECTANGLE,{x:0,y:5.2,w:10,h:.425,fill:{color:C.strong,transparency:30}});}

 await pres.writeFile({fileName:"e:/CodeBuddyprojects/Elearning/docs/E-Learning比赛项目讲解.pptx"});
 console.log("PPT生成成功！");
}
main().catch(e=>{console.error(e);process.exit(1);});
