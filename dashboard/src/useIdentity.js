import { useCallback, useState } from 'react';
import { clearIdentity, getIdentity, setIdentity } from './identity.js';

/**
 * @returns {{
 *   identity: {employeeId: string, name: string, department: string} | null,
 *   save: (fields: {employeeId: string, name?: string, department?: string}) => void,
 *   clear: () => void,
 * }}
 */
export function useIdentity() {
  const [identity, setIdentityState] = useState(() => getIdentity());
  const save = useCallback((fields) => {
    setIdentityState(setIdentity(fields));
  }, []);
  const clear = useCallback(() => {
    clearIdentity();
    setIdentityState(null);
  }, []);
  return { identity, save, clear };
}
