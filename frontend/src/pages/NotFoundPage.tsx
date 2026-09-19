import React from 'react'
import { Link } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import Button from '@/components/ui/Button'
import { useT } from '@/i18n/react'

const NotFoundPage: React.FC = () => {
  const t = useT()

  return (
    <>
      <Helmet>
        <title>{t('notFound.documentTitle')}</title>
        <meta name="description" content={t('notFound.documentDescription')} />
      </Helmet>

      <div className="min-h-screen bg-dark-950 flex items-center justify-center">
        <div className="text-center">
          <div className="text-6xl font-bold text-primary-500 mb-4">404</div>
          <h1 className="text-3xl font-bold text-white mb-4">{t('notFound.title')}</h1>
          <p className="text-secondary-400 mb-8">{t('notFound.body')}</p>
          <Button asChild>
            <Link to="/">{t('notFound.goHome')}</Link>
          </Button>
        </div>
      </div>
    </>
  )
}

export default NotFoundPage
