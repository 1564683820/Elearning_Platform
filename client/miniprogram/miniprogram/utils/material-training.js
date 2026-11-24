function questionView(question, result) {
  const content = question?.content || {};
  const answer = result?.correct_answer;
  const correctIndex = typeof answer === 'number' ? answer
    : typeof answer === 'string' && /^[A-Z]$/.test(answer) ? answer.charCodeAt(0) - 65
      : typeof answer === 'string' && /^\d+$/.test(answer) ? Number(answer) : -1;
  return {
    stem: content.stem || content.question || '',
    options: content.options || [],
    correctIndex,
    explanation: result?.analysis?.explanation || '',
  };
}

async function submitChoice(page, indexKey, event, api) {
  if (page.data.answered || page.data.submitting || page.data.mode !== 'question') return;
  const question = page.data.questions[page.data[indexKey]];
  const index = Number(event.currentTarget.dataset.index);
  if (!question || !Number.isInteger(index) || index < 0 || index >= (question.content?.options || []).length) return;
  const generation = page._round || 0;
  const isCurrent = () => (page._round || 0) === generation && page.data.mode === 'question'
    && page.data.questions[page.data[indexKey]] === question;
  page.setData({ submitting: true, selectedIndex: index });
  try {
    const result = await api.submitAnswer({
      questionId: question.id, answer: index,
      timeSpent: Math.max(0, Math.floor((Date.now() - (page.data.questionStartedAt || Date.now())) / 1000)),
    });
    if (!isCurrent()) return;
    page.setData({
      answered: true, showAnalysis: true,
      correctCount: page.data.correctCount + (result.is_correct ? 1 : 0),
      wrongCount: (page.data.wrongCount || 0) + (result.is_correct ? 0 : 1),
      question: questionView(question, result),
    });
  } catch (error) {
    if (isCurrent()) {
      page.setData({ selectedIndex: -1 });
      wx.showToast({ title: '提交失败，请重试', icon: 'none' });
    }
  } finally {
    if (isCurrent()) page.setData({ submitting: false });
  }
}

module.exports = { questionView, submitChoice };
