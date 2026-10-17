// Pure helpers for rendering the authenticated user's profile.
// Kept free of React Native imports so they can be unit-tested under Node.

function asTrimmedText(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

export function buildProfileFields(profile) {
  const source = profile && typeof profile === 'object' ? profile : {};

  let accountDate = null;
  if (typeof source.created_at === 'string') {
    const parsed = new Date(source.created_at);
    if (Number.isFinite(parsed.getTime())) {
      accountDate = parsed.toLocaleDateString();
    }
  }

  const age = source.age;
  const ageText = age === null || age === undefined ? 'Not provided' : String(age);

  return {
    name: asTrimmedText(source.name) || 'Name not provided',
    rows: [
      { label: 'Phone', value: asTrimmedText(source.phone_number) || 'Not provided' },
      { label: 'Email', value: asTrimmedText(source.email) || 'Not provided' },
      { label: 'Phone verification', value: source.phone_verified ? 'Verified' : 'Not verified' },
      { label: 'Age', value: ageText },
      { label: 'Gender', value: asTrimmedText(source.gender) || 'Not provided' },
      { label: 'Account created', value: accountDate || 'Not available' },
    ],
  };
}
