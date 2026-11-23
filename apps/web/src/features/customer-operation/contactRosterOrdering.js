const scoreValue = (contact) => Number(contact.priority_score || 0);

const positionValue = (contact) => {
  const position = Number(contact.position);
  return Number.isFinite(position) && position > 0 ? position : Number.MAX_SAFE_INTEGER;
};

const nameValue = (contact) => String(contact.full_name || '');

export const sortActiveRosterContacts = (contacts) => [...contacts].sort((left, right) => {
  const pinnedDifference = Number(Boolean(right.is_pinned)) - Number(Boolean(left.is_pinned));
  if (pinnedDifference !== 0) return pinnedDifference;

  const scoreDifference = scoreValue(right) - scoreValue(left);
  if (scoreDifference !== 0) return scoreDifference;

  const positionDifference = positionValue(left) - positionValue(right);
  if (positionDifference !== 0) return positionDifference;

  return nameValue(left).localeCompare(nameValue(right));
});

export const sortBackupRosterContacts = (contacts) => [...contacts].sort((left, right) => {
  const scoreDifference = scoreValue(right) - scoreValue(left);
  if (scoreDifference !== 0) return scoreDifference;

  return nameValue(left).localeCompare(nameValue(right));
});
