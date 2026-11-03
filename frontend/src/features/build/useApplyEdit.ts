import { useNavigate } from 'react-router-dom';

import type { ModificationOut, ModificationRequest } from '../../api/types';
import { notifyError } from '../../lib/notify';
import { useModifyBuild } from './api';

/** Состояние перехода на новую сборку: разница с прежней. */
export interface EditNavigationState {
  modification: ModificationOut;
}

/** Применяет правку и переходит на новую сборку; ошибку показывает уведомлением. */
export function useApplyEdit(buildId: string) {
  const navigate = useNavigate();
  const modify = useModifyBuild(buildId);
  const apply = (request: ModificationRequest, onDone?: () => void) =>
    modify.mutate(request, {
      onSuccess: (modification) => {
        onDone?.();
        const state: EditNavigationState = { modification };
        navigate(`/builds/${modification.build.id}`, { state });
      },
      onError: notifyError,
    });
  return { apply, isPending: modify.isPending };
}
