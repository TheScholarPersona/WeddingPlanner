import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import { Button } from '@/components/ui/button';

import { AuthLayout } from './AuthLayout';
import { useLogout } from './session';

export function NoAccessPage() {
  const { t } = useTranslation();
  const logout = useLogout();
  const navigate = useNavigate();
  return (
    <AuthLayout title={t('auth.noAccess.title')} subtitle={t('auth.noAccess.body')}>
      <Button
        variant="secondary"
        onClick={() => logout.mutate(undefined, { onSettled: () => void navigate('/login') })}
      >
        {t('nav.signOut')}
      </Button>
    </AuthLayout>
  );
}
