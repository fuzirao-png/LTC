const intentLabels = {
  interested: '\u6709\u5174\u8da3',
  pricing: '\u8be2\u4ef7',
  product_question: '\u4ea7\u54c1\u95ee\u9898',
  not_interested: '\u6682\u4e0d\u8003\u8651',
  unsubscribe: '\u9000\u8ba2',
  proposal: '\u65b9\u6848/\u62a5\u4ef7',
  won: '\u5df2\u6210\u4ea4',
  automatic_reply: '\u81ea\u52a8\u56de\u590d',
};

const intentActionLabels = {
  interested: '\u5efa\u8bae\u5c3d\u5feb\u8054\u7cfb\u5ba2\u6237\uff0c\u786e\u8ba4\u5177\u4f53\u9700\u6c42\u5e76\u63a8\u8fdb\u6c9f\u901a\u3002',
  pricing: '\u5efa\u8bae\u53d1\u9001\u62a5\u4ef7\u6216\u4ef7\u683c\u8d44\u6599\uff0c\u786e\u8ba4\u9884\u7b97\u548c\u91c7\u8d2d\u65f6\u95f4\u3002',
  product_question: '\u5efa\u8bae\u9488\u5bf9\u5ba2\u6237\u95ee\u9898\u63d0\u4f9b\u51c6\u786e\u7b54\u590d\u548c\u76f8\u5173\u4ea7\u54c1\u8d44\u6599\u3002',
  not_interested: '\u5efa\u8bae\u6682\u505c\u672c\u8f6e\u8ddf\u8fdb\uff0c\u5408\u9002\u65f6\u518d\u8054\u7cfb\u3002',
  unsubscribe: '\u5efa\u8bae\u5c06\u8be5\u8054\u7cfb\u4eba\u79fb\u51fa\u8425\u9500\u89e6\u8fbe\u540d\u5355\u3002',
  proposal: '\u5efa\u8bae\u51c6\u5907\u5e76\u53d1\u9001\u9488\u5bf9\u6027\u65b9\u6848\u6216\u62a5\u4ef7\u3002',
  won: '\u5ba2\u6237\u5df2\u6210\u4ea4\uff0c\u5efa\u8bae\u505c\u6b62\u81ea\u52a8\u89e6\u8fbe\u3002',
  automatic_reply: '\u81ea\u52a8\u56de\u590d',
};

const containsChinese = (value) => /[\u3400-\u9fff]/.test(value);

export const previewReplyContent = (content) => {
  const value = String(content || '').trim();
  return value.length > 120 ? `${value.slice(0, 120)}...` : value || '-';
};

export const formatReplyAnalysis = (analysis = {}) => {
  const intentLevel = String(analysis.intentLevel || '').trim();
  const nextAction = String(analysis.nextAction || '').trim();
  const evidenceQuote = String(analysis.evidenceQuote || '').trim();
  const automaticReply = intentLevel === 'automatic_reply';

  return {
    intent: intentLabels[intentLevel] || (intentLevel ? '\u5176\u4ed6\u610f\u56fe' : '\u672a\u5206\u6790'),
    nextAction: automaticReply
      ? ''
      : containsChinese(nextAction)
        ? nextAction
        : intentActionLabels[intentLevel] || '\u5efa\u8bae\u4eba\u5de5\u67e5\u770b\u90ae\u4ef6\u5185\u5bb9\u540e\u786e\u8ba4\u5904\u7406\u65b9\u5f0f\u3002',
    evidence: containsChinese(evidenceQuote)
      ? evidenceQuote
      : evidenceQuote
        ? '\u8bf7\u7ed3\u5408\u5ba2\u6237\u539f\u59cb\u90ae\u4ef6\u6b63\u6587\u5224\u65ad\u3002'
        : '',
  };
};

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export const displayFailureCompany = (failure = {}) => {
  const companyName = String(failure.companyName || '').trim();
  if (companyName && !uuidPattern.test(companyName)) return companyName;
  return '\u672a\u77e5\u516c\u53f8';
};
