import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Dialog } from '@/components/Dialog';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { isoDate } from '@/lib/format';

import {
  eventsPath,
  fromLocalInputs,
  toLocalInputs,
  type CalendarEvent,
  type EventInput,
} from './api';

interface Props {
  org: string;
  projectId: string;
  event?: CalendarEvent;
  onClose: () => void;
}

export function EventDialog({ org, projectId, event, onClose }: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const start = event && !event.all_day ? toLocalInputs(event.starts_at) : null;
  const end = event?.ends_at && !event.all_day ? toLocalInputs(event.ends_at) : null;
  const [title, setTitle] = useState(event?.title ?? '');
  const [allDay, setAllDay] = useState(event?.all_day ?? false);
  const [date, setDate] = useState(event ? (start?.date ?? event.start_date) : isoDate(new Date()));
  const [startTime, setStartTime] = useState(start?.time ?? '10:00');
  const [endTime, setEndTime] = useState(end?.time ?? '');
  const [endDate, setEndDate] = useState(event?.all_day ? event.end_date : '');
  const [location, setLocation] = useState(event?.location ?? '');
  const [description, setDescription] = useState(event?.description ?? '');
  const [shared, setShared] = useState(event?.visibility === 'client');

  const done = async () => {
    await queryClient.invalidateQueries({ queryKey: ['org', org] });
    onClose();
  };
  const body = (): EventInput => ({
    title: title.trim(),
    all_day: allDay,
    ...(allDay
      ? { start_date: date, end_date: endDate && endDate > date ? endDate : null }
      : {
          starts_at: fromLocalInputs(date, startTime),
          ends_at: endTime ? fromLocalInputs(date, endTime) : null,
        }),
    location: location.trim() || null,
    description: description.trim() || null,
    visibility: shared ? 'client' : 'internal',
  });
  const save = useMutation({
    mutationFn: () =>
      event
        ? api<CalendarEvent>('PUT', `${eventsPath(org, projectId)}/${event.id}`, body(), {
            'If-Match': `"${event.version}"`,
          })
        : api<CalendarEvent>('POST', eventsPath(org, projectId), body()),
    onSuccess: done,
  });
  const remove = useMutation({
    mutationFn: () => api('DELETE', `${eventsPath(org, projectId)}/${event!.id}`),
    onSuccess: done,
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  const endBeforeStart = !allDay && !!endTime && endTime < startTime;

  return (
    <Dialog title={event ? t('calendar.editEvent') : t('calendar.newEvent')} onClose={onClose}>
      <form className="flex max-h-[75vh] flex-col gap-4 overflow-y-auto pr-1" onSubmit={submit}>
        <Field id="event-title" label={t('calendar.eventTitle')}>
          <Input
            id="event-title"
            required
            maxLength={200}
            placeholder={t('calendar.titlePlaceholder')}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <label className="flex items-center gap-2.5 text-sm">
          <input
            type="checkbox"
            className="size-4 accent-accent"
            checked={allDay}
            onChange={(e) => setAllDay(e.target.checked)}
          />
          {t('calendar.allDay')}
        </label>
        <div className="grid grid-cols-2 gap-3">
          <Field id="event-date" label={allDay ? t('calendar.from') : t('calendar.date')}>
            <Input
              id="event-date"
              type="date"
              required
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </Field>
          {allDay ? (
            <Field id="event-end-date" label={t('calendar.until')}>
              <Input
                id="event-end-date"
                type="date"
                min={date}
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </Field>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <Field id="event-start" label={t('calendar.start')}>
                <Input
                  id="event-start"
                  type="time"
                  required
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                />
              </Field>
              <Field id="event-end" label={t('calendar.end')}>
                <Input
                  id="event-end"
                  type="time"
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                />
              </Field>
            </div>
          )}
        </div>
        <Field id="event-location" label={t('calendar.location')}>
          <Input
            id="event-location"
            maxLength={300}
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          />
        </Field>
        <Field id="event-notes" label={t('calendar.notes')} hint={t('calendar.notesHint')}>
          <Textarea
            id="event-notes"
            rows={3}
            maxLength={5000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <label className="flex items-start gap-2.5 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 size-4 accent-accent"
            checked={shared}
            onChange={(e) => setShared(e.target.checked)}
          />
          <span>
            {t('calendar.shareWithCouple')}
            <span className="block text-xs text-muted">{t('calendar.shareHint')}</span>
          </span>
        </label>
        {endBeforeStart && <FormMessage>{t('calendar.endBeforeStart')}</FormMessage>}
        {(save.error || remove.error) && (
          <FormMessage>{errorMessage(save.error ?? remove.error, t)}</FormMessage>
        )}
        <div className="flex flex-wrap justify-between gap-2">
          {event ? (
            <Button
              type="button"
              variant="ghost"
              className="text-danger"
              disabled={remove.isPending}
              onClick={() => {
                if (window.confirm(t('calendar.confirmDelete'))) remove.mutate();
              }}
            >
              {t('common.delete')}
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={save.isPending || endBeforeStart}>
              {event ? t('common.save') : t('calendar.addEvent')}
            </Button>
          </div>
        </div>
      </form>
    </Dialog>
  );
}
