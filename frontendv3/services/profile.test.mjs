import test from 'node:test';
import assert from 'node:assert/strict';
import { buildProfileFields } from './profile.mjs';

test('renders provided profile fields', () => {
  const view = buildProfileFields({
    name: '  Synthetic User  ',
    phone_number: '+15555550123',
    phone_verified: true,
    age: 30,
    gender: 'other',
    created_at: '2026-01-02T00:00:00Z',
  });

  assert.equal(view.name, 'Synthetic User');
  const byLabel = Object.fromEntries(view.rows.map((row) => [row.label, row.value]));
  assert.equal(byLabel.Phone, '+15555550123');
  assert.equal(byLabel['Phone verification'], 'Verified');
  assert.equal(byLabel.Age, '30');
  assert.equal(byLabel.Gender, 'other');
  assert.notEqual(byLabel['Account created'], 'Not available');
});

test('handles missing and null fields gracefully', () => {
  const view = buildProfileFields({ name: '', phone_number: null, age: null, gender: '   ' });

  assert.equal(view.name, 'Name not provided');
  const byLabel = Object.fromEntries(view.rows.map((row) => [row.label, row.value]));
  assert.equal(byLabel.Phone, 'Not provided');
  assert.equal(byLabel.Email, 'Not provided');
  assert.equal(byLabel['Phone verification'], 'Not verified');
  assert.equal(byLabel.Age, 'Not provided');
  assert.equal(byLabel.Gender, 'Not provided');
  assert.equal(byLabel['Account created'], 'Not available');
});

test('does not throw for an absent or invalid profile', () => {
  for (const value of [undefined, null, 'not-an-object', 42]) {
    const view = buildProfileFields(value);
    assert.equal(view.name, 'Name not provided');
    assert.equal(view.rows.length, 6);
  }
});

test('treats an invalid created_at as unavailable', () => {
  const view = buildProfileFields({ name: 'Synthetic', created_at: 'not-a-date' });
  const byLabel = Object.fromEntries(view.rows.map((row) => [row.label, row.value]));
  assert.equal(byLabel['Account created'], 'Not available');
});
