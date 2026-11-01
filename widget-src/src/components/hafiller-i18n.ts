import { useEffect, useState } from 'react';

// 网站语言约定：<html lang> 为 'en' 时英文，其余中文；web/i18n.js 切换后派发 mb:langchange。
// 机器人在 Shadow DOM 里，i18n.js 的词典替换进不来，界面文字都在这里维护。
export type Lang = 'zh' | 'en';

export function pageLang(): Lang {
  return document.documentElement.lang.startsWith('en') ? 'en' : 'zh';
}

export function useLang(): Lang {
  const [lang, setLang] = useState<Lang>(pageLang);
  useEffect(() => {
    const sync = () => setLang(pageLang());
    // i18n.js 可能比机器人晚加载，启动时只改 lang 属性不派发事件，所以同时观察 lang 属性。
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
    document.addEventListener('mb:langchange', sync);
    sync();
    return () => { observer.disconnect(); document.removeEventListener('mb:langchange', sync); };
  }, []);
  return lang;
}

type Lead = { products: string; country: string; type: string; quantity: string; delivery: string; contact: string };

const zh = {
  welcome: '您好，我是 HAFILLER 询盘小助手。\n可以帮您查参数、了解资质资料、整理采购需求。想先了解什么？',
  panel: 'HAFILLER 询盘客服',
  title: 'HAFILLER 小助手',
  subtitle: '产品询盘 · 随时为您解答',
  close: '收起客服',
  modes: '回复模式',
  rules: '规则库',
  ai: 'AI 模式',
  reset: '新对话',
  noteAi: 'AI 根据现有资料回答，未确认信息请由销售核实。',
  noteRules: '根据现有产品资料回答，未确认信息交由人工核实。',
  thinking: '正在整理回复',
  progressTitle: '预计进度',
  stages: ['理解问题', '查产品资料', '生成回答', '合规校验'],
  slowHint: '回复未通过校验时会自动改写，请稍候。',
  leadTitle: '整理采购需求',
  leadClose: '关闭需求表',
  country: '国家 / 地区',
  countryPh: '例如：新加坡',
  type: '客户类型',
  types: ['经销商', '医院 / 诊所', '进口商', '其他'],
  quantity: '采购数量',
  quantityPh: '例如：100 支',
  delivery: '期望交期',
  optional: '选填',
  contact: '商务联系方式',
  contactPh: '选填 · 邮箱或电话',
  privacy: '信息仅整理在当前对话中，请勿填写患者资料。',
  submit: '生成询盘摘要 ↗',
  summary: (d: Lead) => `采购需求（尚未提交）\n产品：${d.products}\n国家/地区：${d.country}\n客户类型：${d.type}\n数量：${d.quantity}\n期望交期：${d.delivery || '待确认'}\n联系方式：${d.contact || '未提供'}\n\n请复制需求后自行发送给销售。当前页面尚未配置销售接收渠道。`,
  pick: '勾选产品（可多选）',
  picked: (n: number) => `${n} 款已选`,
  knowledgeError: '导入资料暂未加载，请重新打开客服重试。',
  chips: ['产品参数', '认证资料', '物流售后'],
  leadChip: '整理采购需求 ↗',
  placeholder: '输入问题，例如：Derm 浓度多少？',
  inputLabel: '输入客服问题',
  sendLabel: '发送消息',
  footer: '产品资料仅供询盘参考',
  copy: '复制对话',
  copied: '已复制',
  copyFailed: '复制失败，请手动选择文字',
  customer: '客户',
  agent: '客服',
  openLabel: '打开产品客服',
  closeLabel: '收起产品客服',
  launcher: '产品咨询',
  selectedPrefix: '当前勾选产品：',
  join: '、',
  errAi: 'AI 服务暂不可用，请稍后再试。',
  errNetwork: '连接失败，请重试。',
  errTimeout: '等待超时，请重试或切换规则库。',
  imported: '（导入资料）',
  source: '来源：',
  importedSource: '管理员导入，待核实',
  importedNote: '仅供询盘参考，具体适用范围以正式文件为准。',
};

type Strings = typeof zh;

const en: Strings = {
  welcome: 'Hello, I am the HAFILLER inquiry assistant.\nI can look up specifications, explain certificate status and help you prepare a purchase request. What would you like to know?',
  panel: 'HAFILLER inquiry assistant',
  title: 'HAFILLER Assistant',
  subtitle: 'Product Inquiry · here to help',
  close: 'Close assistant',
  modes: 'Reply mode',
  rules: 'Rule base',
  ai: 'AI mode',
  reset: 'New chat',
  noteAi: 'AI answers from current product documents. Unconfirmed details are verified by sales.',
  noteRules: 'Answers come from current product documents. Unconfirmed details are verified by our team.',
  thinking: 'Preparing reply',
  progressTitle: 'Estimated progress',
  stages: ['Understanding the question', 'Checking product documents', 'Writing the reply', 'Compliance check'],
  slowHint: 'Replies that fail the compliance check are rewritten automatically. Please wait.',
  leadTitle: 'Prepare purchase request',
  leadClose: 'Close request form',
  country: 'Country / region',
  countryPh: 'e.g. Singapore',
  type: 'Customer type',
  types: ['Distributor', 'Hospital / clinic', 'Importer', 'Other'],
  quantity: 'Quantity',
  quantityPh: 'e.g. 100 syringes',
  delivery: 'Expected delivery',
  optional: 'Optional',
  contact: 'Business contact',
  contactPh: 'Optional · email or phone',
  privacy: 'This stays in the current chat only. Do not enter patient information.',
  submit: 'Create inquiry summary ↗',
  summary: (d: Lead) => `Purchase request (not submitted)\nProducts: ${d.products}\nCountry/region: ${d.country}\nCustomer type: ${d.type}\nQuantity: ${d.quantity}\nExpected delivery: ${d.delivery || 'to be confirmed'}\nContact: ${d.contact || 'not provided'}\n\nPlease copy this request and send it to our sales team yourself. This page is not yet connected to a sales channel.`,
  pick: 'Select products (multiple allowed)',
  picked: (n: number) => `${n} selected`,
  knowledgeError: 'Imported product documents did not load. Close and reopen the assistant to retry.',
  chips: ['Specifications', 'Certificates', 'Shipping & after-sales'],
  leadChip: 'Prepare purchase request ↗',
  placeholder: 'Ask a question, e.g. What is the concentration of Derm?',
  inputLabel: 'Type your question',
  sendLabel: 'Send message',
  footer: 'Product information is for inquiry reference only',
  copy: 'Copy chat',
  copied: 'Copied',
  copyFailed: 'Copy failed. Please select the text manually.',
  customer: 'Customer',
  agent: 'Assistant',
  openLabel: 'Open product assistant',
  closeLabel: 'Close product assistant',
  launcher: 'Product Inquiry',
  selectedPrefix: 'Selected products: ',
  join: ', ',
  errAi: 'The AI service is unavailable. Please try again later.',
  errNetwork: 'Connection failed. Please try again.',
  errTimeout: 'The reply timed out. Please try again or switch to Rule base.',
  imported: ' (imported document)',
  source: 'Source: ',
  importedSource: 'Imported by administrator, to be verified',
  importedNote: 'For inquiry reference only. Indications are subject to the official documents.',
};

export const strings: Record<Lang, Strings> = { zh, en };
