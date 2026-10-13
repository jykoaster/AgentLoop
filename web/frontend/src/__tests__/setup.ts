import { config } from '@vue/test-utils'
import { library } from '@fortawesome/fontawesome-svg-core'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import { ICONS } from '../icons'

library.add(...ICONS)
config.global.components.FontAwesomeIcon = FontAwesomeIcon
