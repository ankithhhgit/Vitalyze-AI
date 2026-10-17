export interface ProfileRow {
  label: string;
  value: string;
}

export interface ProfileFields {
  name: string;
  rows: ProfileRow[];
}

export function buildProfileFields(profile: unknown): ProfileFields;
