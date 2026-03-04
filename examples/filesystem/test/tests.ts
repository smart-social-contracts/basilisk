import { Test } from 'azle/test';
import { _SERVICE } from './dfx_generated/filesystem/filesystem.did';
import { ActorSubclass } from '@dfinity/agent';

export function getTests(actor: ActorSubclass<_SERVICE>): Test[] {
    return [
        {
            name: 'test_fs_mkdir_and_listdir',
            test: async () => {
                const result = await actor.test_fs_mkdir_and_listdir();
                return {
                    Ok: result.includes('subdir')
                };
            }
        },
        {
            name: 'test_fs_write_and_read',
            test: async () => {
                const result = await actor.test_fs_write_and_read();
                return {
                    Ok: result === 'hello from ic-wasi-polyfill'
                };
            }
        },
        {
            name: 'test_fs_path_exists',
            test: async () => {
                const result = await actor.test_fs_path_exists();
                // [exists=True, nonexistent=False, isdir=True, isfile=True]
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
                // [st_size=10, st_size==10 is True]
                return {
                    Ok: result[0] === '10' && result[1] === 'True'
                };
            }
        },
        {
            name: 'test_fs_remove_and_rename',
            test: async () => {
                const result = await actor.test_fs_remove_and_rename();
                // [removed=False, old_name=False, new_name=True]
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
