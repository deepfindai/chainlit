import { useAuth } from 'api/auth';
import { Navigate } from 'react-router-dom';
import { useRecoilValue } from 'recoil';

import { Alert, Box, Stack } from '@mui/material';

import { Header } from 'components/organisms/header';
import { ThreadHistorySideBar } from 'components/organisms/threadHistory/sidebar';

import { projectSettingsState } from 'state/project';
import { userEnvState } from 'state/user';

type Props = {
  children: JSX.Element;
};

const Page = ({ children }: Props) => {
  const { isAuthenticated } = useAuth();
  const projectSettings = useRecoilValue(projectSettingsState);
  const userEnv = useRecoilValue(userEnvState);

  if (projectSettings?.userEnv) {
    for (const key of projectSettings.userEnv || []) {
      if (!userEnv[key]) return <Navigate to="/env" />;
    }
  }

  if (!isAuthenticated) {
    const [searchParams] = useSearchParams();
    const token = searchParams.get('token');
    if (token) {
      document.cookie = 'token=' + token;
    }
    return <Navigate to="/login" />;
  }

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        width: '100%'
      }}
    >
      <Header projectSettings={projectSettings} />
      {!isAuthenticated ? (
        <Alert severity="error">You are not part of this project.</Alert>
      ) : (
        <Stack direction="row" height="100%" width="100%" overflow="auto">
          <ThreadHistorySideBar />
          {children}
        </Stack>
      )}
    </Box>
  );
};

export default Page;
