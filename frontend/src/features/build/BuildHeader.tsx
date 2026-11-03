import { ActionIcon, Badge, Button, Group, Stack, Text, TextInput, Title } from '@mantine/core';
import {
  IconBookmark,
  IconBookmarkFilled,
  IconCheck,
  IconDownload,
  IconPencil,
} from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import type { BuildDetail } from '../../api/types';
import { formatDateTime, formatRub } from '../../lib/format';
import { TIER_TITLES } from '../../lib/labels';
import { notifyError } from '../../lib/notify';
import { usePatchBuild } from './api';

interface BuildHeaderProps {
  build: BuildDetail;
}

/** Заголовок сборки: название, цена, сохранение, PDF. */
export function BuildHeader({ build }: BuildHeaderProps) {
  const patch = usePatchBuild(build.id);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(build.title ?? '');
  const fallbackTitle = `Сборка «${TIER_TITLES[build.tier]}»`;

  const saveTitle = () =>
    patch.mutate({ title }, { onSuccess: () => setEditing(false), onError: notifyError });

  return (
    <Stack gap="xs">
      <Group justify="space-between" align="flex-start">
        <Stack gap={4}>
          {editing ? (
            <Group gap="xs">
              <TextInput
                aria-label="Название сборки"
                value={title}
                maxLength={120}
                onChange={(event) => setTitle(event.currentTarget.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') saveTitle();
                }}
              />
              <ActionIcon
                aria-label="Сохранить название"
                onClick={saveTitle}
                loading={patch.isPending}
              >
                <IconCheck size={16} />
              </ActionIcon>
            </Group>
          ) : (
            <Group gap="xs">
              <Title order={2}>{build.title ?? fallbackTitle}</Title>
              <ActionIcon
                variant="subtle"
                color="gray"
                aria-label="Переименовать"
                onClick={() => setEditing(true)}
              >
                <IconPencil size={16} />
              </ActionIcon>
            </Group>
          )}
          <Group gap="xs">
            <Badge variant="light">{TIER_TITLES[build.tier]}</Badge>
            {build.parent_build_id && <Badge variant="outline">после правки</Badge>}
            <Text size="sm" c="dimmed">
              {formatDateTime(build.created_at)} · база знаний {build.kb_version}
            </Text>
          </Group>
        </Stack>
        <Text fz={32} fw={700}>
          {formatRub(build.total_price_kop)}
        </Text>
      </Group>
      <Group gap="sm">
        <Button
          variant={build.is_saved ? 'filled' : 'default'}
          leftSection={
            build.is_saved ? <IconBookmarkFilled size={16} /> : <IconBookmark size={16} />
          }
          loading={patch.isPending}
          onClick={() => patch.mutate({ is_saved: !build.is_saved }, { onError: notifyError })}
        >
          {build.is_saved ? 'Сохранена' : 'Сохранить'}
        </Button>
        <Button
          component="a"
          href={`/api/v1/builds/${build.id}/pdf`}
          download
          variant="default"
          leftSection={<IconDownload size={16} />}
        >
          PDF
        </Button>
        <Button component={Link} to={`/consultations/${build.consultation_id}`} variant="subtle">
          Все варианты
        </Button>
        {build.parent_build_id && (
          <Button component={Link} to={`/builds/${build.parent_build_id}`} variant="subtle">
            Предыдущая версия
          </Button>
        )}
      </Group>
    </Stack>
  );
}
