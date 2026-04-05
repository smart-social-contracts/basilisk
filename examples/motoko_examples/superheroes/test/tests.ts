import { Test } from '../../../_test_lib';

export function getTests(shCanister: any): Test[] {
    return [
        {
            name: 'create superhero',
            test: async () => {
                const result = await shCanister.create({ name: 'Superman', superpowers: [] });
                return { Ok: result === 0 };
            }
        },
        {
            name: 'read superhero',
            test: async () => {
                const result = await shCanister.read(0);
                return { Ok: result.length === 1 && result[0].name === 'Superman' };
            }
        },
        {
            name: 'update_ superhero',
            test: async () => {
                const result = await shCanister.update_(0, { name: 'Batman', superpowers: [] });
                return { Ok: result === true };
            }
        },
        {
            name: 'read updated superhero',
            test: async () => {
                const result = await shCanister.read(0);
                return { Ok: result.length === 1 && result[0].name === 'Batman' };
            }
        },
        {
            name: 'delete_hero',
            test: async () => {
                const result = await shCanister.delete_hero(0);
                return { Ok: result === true };
            }
        },
        {
            name: 'read deleted superhero',
            test: async () => {
                const result = await shCanister.read(0);
                return { Ok: result.length === 0 };
            }
        }
    ];
}
