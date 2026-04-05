import { Test } from '../../_test_lib';

export function getTests(kvCanister: any): Test[] {
    return [
        {
            name: 'get non-existent key',
            test: async () => {
                const result = await kvCanister.get('nonexistent');
                return { Ok: result.length === 0 || result[0] === undefined };
            }
        },
        {
            name: 'set and get key',
            test: async () => {
                await kvCanister.set('greeting', 'hello');
                const result = await kvCanister.get('greeting');
                return { Ok: result.length === 1 && result[0] === 'hello' };
            }
        },
        {
            name: 'overwrite key',
            test: async () => {
                await kvCanister.set('greeting', 'world');
                const result = await kvCanister.get('greeting');
                return { Ok: result.length === 1 && result[0] === 'world' };
            }
        },
        {
            name: 'set multiple keys',
            test: async () => {
                await kvCanister.set('name', 'basilisk');
                await kvCanister.set('version', '1');
                const name = await kvCanister.get('name');
                const version = await kvCanister.get('version');
                return {
                    Ok:
                        name.length === 1 && name[0] === 'basilisk' &&
                        version.length === 1 && version[0] === '1'
                };
            }
        }
    ];
}
