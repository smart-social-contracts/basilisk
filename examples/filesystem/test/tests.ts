import { Test } from 'azle/test';
import { _SERVICE } from './dfx_generated/filesystem/filesystem.did';
import { ActorSubclass } from '@dfinity/agent';

export function getTests(actor: ActorSubclass<_SERVICE>): Test[] {
    return [
        {
            name: 'test_fs_diagnostics',
            test: async () => {
                const result = await actor.test_fs_diagnostics();
                console.log('DIAGNOSTICS:', JSON.stringify(result, null, 2));
                return {
                    Ok: result.length > 0
                };
            }
        },
        {
            name: 'test_fs_mkdir_and_listdir',
            test: async () => {
                const result = await actor.test_fs_mkdir_and_listdir();
                console.log('mkdir_and_listdir result:', JSON.stringify(result));
                return {
                    Ok: result.includes('subdir')
                };
            }
        },
        {
            name: 'test_fs_write_and_read',
            test: async () => {
                const result = await actor.test_fs_write_and_read();
                console.log('write_and_read result:', JSON.stringify(result));
                return {
                    Ok: result === 'hello from ic-wasi-polyfill'
                };
            }
        },
        {
            name: 'test_fs_path_exists',
            test: async () => {
                const result = await actor.test_fs_path_exists();
                console.log('path_exists result:', JSON.stringify(result));
                return {
                    Ok:
                        result[0] === 'True' &&
                        result[1] === 'False' &&
                        result[2] === 'True' &&
                        result[3] === 'True'
                };
            }
        },
        {
            name: 'test_fs_stat',
            test: async () => {
                const result = await actor.test_fs_stat();
                console.log('stat result:', JSON.stringify(result));
                return {
                    Ok: result[0] === '10' && result[1] === 'True'
                };
            }
        },
        {
            name: 'test_fs_remove_and_rename',
            test: async () => {
                const result = await actor.test_fs_remove_and_rename();
                console.log('remove_and_rename result:', JSON.stringify(result));
                return {
                    Ok:
                        result[0] === 'False' &&
                        result[1] === 'False' &&
                        result[2] === 'True'
                };
            }
        }
    ];
}
